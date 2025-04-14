
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
from pydantic import BaseModel, conlist
import logging
import time
from openai import OpenAI
import os
import asyncio
from datetime import datetime, timedelta
import redis
import hashlib
from celery import Celery
from celery.result import AsyncResult
import json

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
    recommendations: conlist(ARFIDRecommendation, min_items=20)
    notes: list[ARFIDNotes]

app = Flask(__name__)

CORS(app)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(default_headers={"OpenAI-Beta": "assistants=v2"})

instructions = """
You are an expert in Avoidant/Restrictive Food Intake Disorder. In order to broaden patients' diets, you use food chaining to create 20 recommendations based on their safe products. When you receive a message, you'll respond with at least 20 options
Remember, the recommendations.length >= 20.
"""

app.config["SESSION_TYPE"]="redis"
app.config["SESSION_PERMANENT"]=False
app.config["SESSION_USE_SIGNER"]=True
app.config["SESSION_KEY_PREFIX"]="flask_session:"
app.config["SESSION_REDIS"]=redis.from_url(os.environ.get("REDISCLOUD_URL"))
app.config["SECRET_KEY"]=os.environ.get("FLASK_SECRET_KEY")
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
redis_client = redis.from_url(os.environ.get("REDISCLOUD_URL"))


ongoing_tasks = {}
assistants = {}

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        # Flask-CORS will handle OPTIONS automatically.
        return '', 200
    
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
        
        file_ids = []
        for file_stream in file_streams:
            uploaded_file = client.files.create(file=file_stream, purpose="assistants")
            file_ids.append(uploaded_file.id)  # Collect the file_id
            file_stream.close()  # Close the file stream after uploading

        assistants = client.beta.assistants.create(
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

@app.route("/api/end", methods=["POST"])
def end():
    try:
        data = request.get_json()
        assistant_key = data.get("assistant_key")
        if not assistant_key:    
            return jsonify({"error": "No assistant found"}), 400
        redis_key= f"assistant:{assistant_key}"
        raw_assistant_id = redis_client.get(redis_key)
        if not raw_assistant_id:
            return jsonify({"error": "Assistant not found in Redis or expired"}), 400
        raw_assistant_id = raw_assistant_id.decode("utf-8")
        client.beta.assistants.delete(raw_assistant_id)
        logger.info(f"Assistant with ID {raw_assistant_id} deleted.")
        session.pop('assistant_key', None)
        redis_client.delete(redis_key)
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
        assistant_key = data.get("assistant_key")
        if (initial and not prompt1 and not prompt2 and not prompt3) or (not initial and not update):
            return jsonify( { "error": "All inputs are required" }, status=400 )
     
        if initial:
            # Create a new thread for the first message
            thread =  client.beta.threads.create()
            thread_id = thread.id
            os.environ["THREAD_ID"] = thread_id
            client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=f"Include these foods of patients {prompt1}"
            )
            client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=f"Do not include these foods patient doesn't like or eats: {prompt2}"
            )
            client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=f"Patient is alleric or has restrictions and can't eat: {prompt3}"
            )
        else: 
            thread_id = os.environ.get("THREAD_ID")
            client.beta.threads.messages.create(
                thread_id=thread_id, content=update, role="user"
            )
        if not assistant_key:
            return jsonify({"error": "Assistant not found in session"}), 400
        redis_key= f"assistant:{assistant_key}"
        raw_assistant_id = redis_client.get(redis_key)
        if not raw_assistant_id:
            return jsonify({"error": "Assistant not found in Redis or expired"}), 400
        raw_assistant_id = raw_assistant_id.decode("utf-8")
        # task = asyncio.create_task(run_openai(thread_id, raw_assistant_id))
        # ongoing_tasks[task_id] = task
        task = run_openai_task.apply_async(args=[thread_id, raw_assistant_id])

        return jsonify({"task_id": task.id}), 202
    except Exception as e:
        logger.error(f"Error in /create_message: {str(e)}")
        return jsonify(error=str(e), status=500)

@celery.task 
def run_openai_task(thread_id, assistant_id):
    logger.info(f"Running OpenAI task with thread ID: {thread_id} and assistant ID: {assistant_id}")
    try:
        with app.app_context():
            runs = client.beta.threads.runs.create(
              thread_id=thread_id, assistant_id=assistant_id, instructions=instructions,
              response_format={
                  "type": "json_schema",
                  "json_schema": {
                      "name": "arfid_schema",
                      "schema": ARFIDResponse.model_json_schema(),
                  }
              }
            )
            while True:
                run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=runs.id)

                logger.info(f"Run status: {run.status}")
                if run.status == "completed":
                    messages =  client.beta.threads.messages.list(thread_id=thread_id)
                    assistant_messages = []
                    logger.info(f"Messages: {messages.data}")
                    if len(messages.data) > 0:
                        for msg in messages.data:
                            if msg.role == "assistant":
                                logger.info(f"Assistant message: {msg}")
                                logger.info(f"Assistant role message: {msg.role}")
                                assistant_messages.append({ "role": msg.role, "content": msg.content })
                    logger.info(f"Type Assistant messages: {type(assistant_messages)}")
                    logger.info(f"Assistant messages: {assistant_messages}")
                    return assistant_messages[0]["content"][0].text.value
                time.sleep(5)
    except Exception as e:
        logger.error(f"Error in run_openai: {str(e)}")
        return {"error": str(e), "status": 500}
    
@app.route('/api/update_with_selections', methods=['POST'])
def submit_recommendations():
    data = request.get_json()
    recommendations = data.get("recommendations")
    assistant_key = data.get("assistant_key")
    update = data.get("update")
    # Process the recommendations and notes as needed
    logger.info(f"Recommendations: {recommendations}")
    thread_id = os.environ.get("THREAD_ID")
    client.beta.threads.messages.create(
        thread_id=thread_id, content=f"Updates from user: {update}", role="user"
    )
    client.beta.threads.messages.create(
        thread_id=thread_id, content=f"The user has provided the following recommendations: {recommendations}, please give more suggestions like that.", role="user"
    )
    client.beta.threads.messages.create(
        thread_id=thread_id, content="Please provide 20 ßrecommendations in the same format as before.", role="user"
    )
    if not assistant_key:
        return jsonify({"error": "Assistant not found in session"}), 400
    redis_key= f"assistant:{assistant_key}"
    raw_assistant_id = redis_client.get(redis_key)
    if not raw_assistant_id:
        return jsonify({"error": "Assistant not found in Redis or expired"}), 400
    raw_assistant_id = raw_assistant_id.decode("utf-8")
    task = run_openai_task.apply_async(args=[thread_id, raw_assistant_id])
    return jsonify({"task_id": task.id}), 202

@app.route('/api/get_message', methods=['POST'])
def get_message():
    data = request.get_json()
    task_id = data.get("task_id")
    logger.info(f"Getting message for task_id: {task_id}")
    if not task_id:
        return jsonify({"error": "task_id is required"}), 400
    task = AsyncResult(task_id, app=celery)
    logger.info(f"Task: {task}")
    logger.info(f"Task result: {task.result}")
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
    
if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)
        