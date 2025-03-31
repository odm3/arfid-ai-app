
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
import logging
import time
from openai import OpenAI
import os
import asyncio
from datetime import datetime, timedelta
from celery import Celery
from celery.result import AsyncResult


app = Flask(__name__)

CORS(app)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(default_headers={"OpenAI-Beta": "assistants=v2"})

vector_store = client.vector_stores.create(name="ARFID Assisting Document")
instructions = """
You are an expert in Avoidant/Restrictive Food Intake Disorder. In order to broaden patients' diets, you use food chaining to create recommendations based on their safe products. You are particularly aware of their allergies, ensuring that you never make a recommendation that they are allergic to. When you receive a message, you'll respond with at least 20 options. Format the response based on the provided JSON Structure.

{
  "example_format": {
    "title": "ARFID Assistant",
    "description": "This tool assists medical professionals and patients with identifying food options for patients with ARFID.",
    "recommendations": [
      {
        "category": "Category 1",
        "foods": [
          {
            "food": "Example food",
            "ingredients": ["Example ingredient 1", "Example ingredient 2"],
            "goal": "Example goal for the food."
          }
        ]
      },
      {
        "category": "Category 2",
        "foods": [
          {
            "food": "Example food",
            "ingredients": ["Example ingredient 1", "Example ingredient 2"],
            "goal": "Example goal for the food."
          }
        ]
      }
    ],
    "notes": [
      {
        "type": "allergen_considerations",
        "content": "Allergen considerations based on the provided foods."
      },
      {
        "type": "goals",
        "content": "General goals of the recommendations. Nutritional and medical focus."
      }
    ]
  }
}
"""

app.config["SESSION_TYPE"]="redis"
app.config["SESSION_PERMANENT"]=False
app.config["SESSION_USE_SIGNER"]=True
app.config["SESSION_KEY_PREFIX"]="flask_session:"
app.config["SESSION_REDIS"]=os.environ.get("REDISCLOUD_URL")
app.config["secret_key"]=os.environ.get("SECRET_KEY")

app.config.update(
    CELERY_BROKER_URL=os.environ.get("REDISCLOUD_URL"),
    CELERY_RESULT_BACKEND=os.environ.get("REDISCLOUD_URL"),
)

Session(app)
celery = Celery(
    app.import_name,
    backend=app.config["CELERY_RESULT_BACKEND"],
    broker=app.config["CELERY_BROKER_URL"]
)

@app.route("/api/start", methods=["GET"])
def start():
    try: 
        directory = "./files"
        file_paths = [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if f.endswith(".pdf") or f.endswith(".png")
        ]
        file_streams = [open(path, "rb") for path in file_paths]
        file_batch = client.vector_stores.file_batches.upload_and_poll(
        vector_store_id=vector_store.id, files=file_streams
        )
        file = client.files.create(
            file=open("files/arfid.json", "rb"), purpose="assistants"
        )

        if file_batch.status != "completed":
            return jsonify({"error": "File upload failed"}), 500
        
        assistants = client.beta.assistants.create(
            name="ARFID Assistant",
            description="This tool assists medical professionals and patients with identifying food options for patients with ARFID.",
            instructions=instructions,
            default_headers={"OpenAI-Beta": "assistants=v2"},
            model="gpt-4o-mini",
            tools=[{"type": "code_interpreter"}, {"type": "file_search"}],
            tool_resources={
                "code_interpreter": {
                    "file_ids": [file.id]
                },
                "file_search": {"vector_store_ids": [vector_store.id]}
            }
        )
        session['assistant_id'] = assistants.id
        logger.info(f"Assistant created with ID: {assistants.id}")
        return jsonify({"assistant_id": assistants.id}), 200
    except Exception as e:
        logger.error(f"Error in /api/start: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/end", methods=["GET"])
def end():
    try:
        assistant_id = session.get('assistant_id')
        if not assistant_id:    
            return jsonify({"error": "No assistant found"}), 400
        client.beta.assistants.delete(assistant_id)
        logger.info(f"Assistant with ID {assistant_id} deleted.")
        session.pop('assistant_id', None)
        return jsonify({"message": "Assistant deleted successfully"}), 200
    except Exception as e:
        logger.error(f"Error in /api/end: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/create_message', methods=['POST'])
def create_message():
    logging.info("Flask route /create_message received a request.")
    query = None
    try:
        data = request.get_json()
        prompt1 = data.get("patient_likes")
        prompt2 = data.get("patient_dislikes")
        prompt3 = data.get("patient_restrictions")
        initial = data.get("initial_request")
        update = data.get("update")
        if (initial and not prompt1 and not prompt2 and not prompt3) or (not initial and not update):
            return jsonify( { "error": "All inputs are required" }, status=400 )
     
        if initial:
            # Create a new thread for the first message
            thread = client.beta.threads.create(
                messages=[
                    {
                        "role": "user",
                        "content": """"
                        Create 20 simple recommendations for a patient with ARFID. The goals output should focus on the nutritional and medical values. Ensure that options provided in the response do not include foods that the patient doesn't like or they have allergies or other dietary restrictions.
                        Categories should be based on the patient's likes. At no point should the patient dislikes be included in the recommendations, or as categories
                        Return exactly 20 recommendations The return result only needs to include the formatted json. 
                        """,
                    }
                ]
            )
            thread_id = thread.id
            os.environ["THREAD_ID"] = thread_id
            query = client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=prompt1
            )
            query = client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=prompt2
            )
            query = client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=prompt3
            )
        else: 
            thread_id = os.environ.get("THREAD_ID")
            query = client.beta.threads.messages.create(
                thread_id=thread_id, content=update, role="user"
            )

        task = run_openai.apply_async(args=[thread_id, session.get('assistant_id')])
        logger.info(f"Task created with ID: {task.id}")
        return jsonify({"task_id": task.id}), 202
    except Exception as e:
        logger.error(f"Error in /create_message: {str(e)}")
        return jsonify(error=str(e), status=500)

@celery.task 
def run_openai(thread_id, assistant_id):
    logger.info(f"Running OpenAI task with thread ID: {thread_id} and assistant ID: {assistant_id}")
    try:
        with app.app_context():
          client = OpenAI(default_headers={"OpenAI-Beta": "assistants=v2"})
          runs = client.beta.threads.runs.create(
              thread_id=thread_id, assistant_id=assistant_id, instructions=instructions
          )
        while True:
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=runs.id)
            if run.status == "completed":
                messages = client.beta.threads.messages.list(thread_id=thread_id)
                last_message = messages.data[0]
                return last_message.content[0].text.value
    except Exception as e:
        return jsonify(error=str(e), status_code=500)


@app.route('/api/get_message/<task_id>', methods=['GET'])
def get_message_status(task_id):
    task = AsyncResult(task_id, app=celery)
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'result': task.result
        }
    else:
        response = {
            'state': task.state,
            'error': str(task.info)
        }
    return jsonify(response)

@app.route('/api/update_with_selections', methods=['POST'])
def submit_recommendations():
    data = request.get_json()
    recommendations = data.get("recommendations")
    update = data.get("update")
    # Process the recommendations and notes as needed
    logger.info(f"Recommendations: {recommendations}")
    thread_id = os.environ.get("THREAD_ID")
    query = client.beta.threads.messages.create(
        thread_id=thread_id, content=update, role="user"
    )
    query2 = client.beta.threads.messages.create(
        thread_id=thread_id, content=f"The user has provided the following recommendations: {recommendations}, please give more suggestions like that.", role="user"
    )
    task = run_openai.apply_async(args=[thread_id])
    logger.info(f"Task created with ID: {task.id}")
    return jsonify({"task_id": task.id}), 202
if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)
        