
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
from pydantic import BaseModel
import logging
import time
from openai import AsyncOpenAI
import os
import asyncio
from datetime import datetime, timedelta
import redis
import hashlib
import uuid

class ARFIDNotes(BaseModel):
    type: str
    content: str

class ARFIDFood(BaseModel):
    food: str
    ingredients: list[str]
    goal: str
class ARFIDRecommendation(BaseModel):
    category: str
    foods: list[ARFIDFood]

class ARFIDResponse(BaseModel):
    title:str
    description:str
    recommendations: list[ARFIDRecommendation]
    notes: list[ARFIDNotes]

app = Flask(__name__)

CORS(app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=True,
    allow_headers="*")
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = AsyncOpenAI(default_headers={"OpenAI-Beta": "assistants=v2"})

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
app.config["SESSION_REDIS"]=redis.from_url(os.environ.get("REDISCLOUD_URL"))
app.config["SECRET_KEY"]=os.environ.get("FLASK_SECRET_KEY")
Session(app)
redis_client = redis.from_url(os.environ.get("REDISCLOUD_URL"))
ongoing_tasks = {}
assistants = {}

@app.route("/api/start", methods=["GET"])
async def start():
    try: 
        directory = "./files"
        file_paths = [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if f.endswith(".pdf") or f.endswith(".png")
        ]
        file_streams = [open(path, "rb") for path in file_paths]
        
        file_ids = []
        for file_stream in file_streams:
            uploaded_file = await client.files.create(file=file_stream, purpose="assistants")
            file_ids.append(uploaded_file.id)  # Collect the file_id
            file_stream.close()  # Close the file stream after uploading

        assistants = await client.beta.assistants.create(
            name="ARFID Assistant",
            description="This tool assists medical professionals and patients with identifying food options for patients with ARFID.",
            instructions=instructions,
            model="gpt-4o-mini",
            tools=[{"type": "code_interpreter"}],
            tool_resources={
                "code_interpreter": {
                    "file_ids": file_ids
                }
            }
        )
        raw_assistant_id = assistants.id
        hashed_key = hashlib.sha256(raw_assistant_id.encode("utf-8")).hexdigest()
        redis_key = f"assistant:{hashed_key}"
        redis_client.set(redis_key, raw_assistant_id)
        session['assistant_key'] = hashed_key
        logger.info(f"Assistant created with ID: {raw_assistant_id} (hashed as: {hashed_key})")
        return jsonify({"assistant_key": hashed_key}), 200
    except Exception as e:
        logger.error(f"Error in /api/start: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/end", methods=["GET"])
async def end():
    try:
        assistant_id = session.get('assistant_id')
        if not assistant_id:    
            return jsonify({"error": "No assistant found"}), 400
        await client.beta.assistants.delete(assistant_id)
        logger.info(f"Assistant with ID {assistant_id} deleted.")
        session.pop('assistant_id', None)
        return jsonify({"message": "Assistant deleted successfully"}), 200
    except Exception as e:
        logger.error(f"Error in /api/end: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/create_message', methods=['POST'])
async def create_message():
    logging.info("Flask route /create_message received a request.")
    query = None
    try:
        data = request.get_json()
        prompt1 = data.get("patient_likes")
        prompt2 = data.get("patient_dislikes")
        prompt3 = data.get("patient_restrictions")
        initial = data.get("initial_request")
        update = data.get("update")
        assistant_key = data.get("assistant_key")
        if (initial and not prompt1 and not prompt2 and not prompt3) or (not initial and not update):
            return jsonify( { "error": "All inputs are required" }, status=400 )
     
        if initial:
            # Create a new thread for the first message
            thread = await client.beta.threads.create(
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
            await client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=prompt1
            )
            await client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=prompt2
            )
            await client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=prompt3
            )
        else: 
            thread_id = os.environ.get("THREAD_ID")
            await client.beta.threads.messages.create(
                thread_id=thread_id, content=update, role="user"
            )
        if not assistant_key:
            return jsonify({"error": "Assistant not found in session"}), 400
        redis_key= f"assistant:{assistant_key}"
        raw_assistant_id = redis_client.get(redis_key)
        if not raw_assistant_id:
            return jsonify({"error": "Assistant not found in Redis or expired"}), 400
        raw_assistant_id = raw_assistant_id.decode("utf-8")
        task_id = str(uuid.uuid4())
        task = asyncio.create_task(run_openai(thread_id, raw_assistant_id))
        ongoing_tasks[task_id] = task

        return jsonify({"task_id": task_id}), 202
    except Exception as e:
        logger.error(f"Error in /create_message: {str(e)}")
        return jsonify(error=str(e), status=500)

async def run_openai(thread_id, assistant_id):
    logger.info(f"Running OpenAI task with thread ID: {thread_id} and assistant ID: {assistant_id}")
    try:
        with app.app_context():
          runs = await client.beta.threads.runs.create_and_poll(
              thread_id=thread_id, assistant_id=assistant_id, instructions=instructions, poll_interval_ms=5000, response_format={
                  "type": "json_schema",
                  "json_schema": {
                      "name": "arfid_schema",
                      "schema": ARFIDResponse.model_json_schema(),
                  }
              }
          )
        if runs.status == "completed":
            messages = await client.beta.threads.messages.list(thread_id=thread_id)
            last_message = messages.data[0]
            return last_message.content[0].text.value
    except Exception as e:
        logger.error(f"Error in run_openai: {str(e)}")
        return jsonify(error=str(e), status_code=500)

@app.route('/api/update_with_selections', methods=['POST'])
async def submit_recommendations():
    data = request.get_json()
    recommendations = data.get("recommendations")
    assistant_key = data.get("assistant_key")
    update = data.get("update")
    # Process the recommendations and notes as needed
    logger.info(f"Recommendations: {recommendations}")
    thread_id = os.environ.get("THREAD_ID")
    await client.beta.threads.messages.create(
        thread_id=thread_id, content=update, role="user"
    )
    await client.beta.threads.messages.create(
        thread_id=thread_id, content=f"The user has provided the following recommendations: {recommendations}, please give more suggestions like that.", role="user"
    )
    if not assistant_key:
        return jsonify({"error": "Assistant not found in session"}), 400
    redis_key= f"assistant:{assistant_key}"
    raw_assistant_id = redis_client.get(redis_key)
    if not raw_assistant_id:
        return jsonify({"error": "Assistant not found in Redis or expired"}), 400
    raw_assistant_id = raw_assistant_id.decode("utf-8")
    task_id = str(uuid.uuid4())
    task = asyncio.create_task(run_openai(thread_id, raw_assistant_id))
    ongoing_tasks[task_id] = task
    return jsonify({"task_id": task_id}), 202


@app.route('/api/get_message/', methods=['POST'])
def get_message():
    data = request.get_json()
    task_id = data.get("task_id")
    logger.info(f"Getting message for task_id: {task_id}")
    if not task_id:
        return jsonify({"error": "task_id is required"}), 400
    if task_id not in ongoing_tasks:
        return jsonify({"error": "task_id not found"}), 404
    task = ongoing_tasks.get(task_id)
    try:
        result = task.result()
        del ongoing_tasks[task_id]
        return jsonify({"result": result}), 200
    except Exception as e:
        logger.error(f"Error in get_message: {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)
        