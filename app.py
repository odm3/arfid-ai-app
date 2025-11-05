
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
from pydantic import BaseModel, model_validator
import logging
import time
from openai import OpenAI
import os
from datetime import datetime, timedelta
import hashlib
from celery import Celery
from celery.result import AsyncResult
import redis
import json

app = Flask(__name__)

CORS(app)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI()

instructions = """
You are an ARFID expert. Based on the imputed safe foods, avoided foods, and restrictions, generate exactly 15 meal recommendations. Each recommendation should build on one of the safe foods or provide an alternative to one of the avoided foods.
Group the recommendations into categories that reflect the input (for example, extra proteins, more vegetables, or additional snacks). 
For each category, provide the list of recommended foods along with a brief transition strategy on how to incorporate these foods gradually. Do not include other food restrictions or any allergy considerations unless specified by the user.
Provide output at around a 6th grade reading level. 

Ensure that the final output contains exactly 15 dishes in total. Use arfid.json as an example of the expected output to be returned.
For every entry in the recommendations list, the sum of all the entry.foods list should equal 15. Keep generating responses if this is less than 15. 
For the transition strategy, provide varied explanations as to how the patient can gradually incorporate these foods into their diet.
The response is being provided to a web API, so just the JSON response is needed. Do not use the word "sneak" or "patient" in the output.

In the allergy considerations, do not provide general safety information. This should be specific to the food items recommended and the entered allergies or restrictions. You should check whether the food item could potentially contain an allergen that the user has specified (e.g, no peanut butter if the user has a peanut allergy). 

In addition, the response should take a subset of recommendations and rank them in ease of implementation, accomplishment, and preparation. This should include 5 of the 20 provided recommendations. 

The return response should be a string of a JSON object. The JSON object needs to match the format of arfid.json The web application will parse it.  
"""

app.config["SESSION_TYPE"]="redis"

app.config["SESSION_PERMANENT"]=False
app.config["SESSION_USE_SIGNER"]=True
app.config["SESSION_KEY_PREFIX"]="flask_session:"
app.config["SESSION_REDIS"]=redis.from_url(os.environ.get("REDIS_URL"))
app.config["SECRET_KEY"]=os.environ.get("FLASK_SECRET_KEY")
app.config.update(
    CELERY_BROKER_URL=os.environ.get("REDIS_URL"),
    CELERY_RESULT_BACKEND=os.environ.get("REDIS_URL"),
)
Session(app)
celery = Celery(
    app.import_name,
    backend=app.config["CELERY_RESULT_BACKEND"],
    broker=app.config["CELERY_BROKER_URL"]
)
redis_client = redis.from_url(os.environ.get("REDIS_URL"))


ongoing_tasks = {}
assistants = {}

# Vector store ID from pre-uploaded PDFs (set via environment variable)
# This is created once by running: python scripts/upload-pdfs-to-openai.py
OPENAI_VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID")

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        # Flask-CORS will handle OPTIONS automatically.
        return '', 200
    
@celery.task
def setup_assistant_task():
    """Background task to set up the assistant using pre-uploaded files"""
    logger.info("Starting assistant setup task...")
    try:
        with app.app_context():
            # Check if vector store ID is configured
            if not OPENAI_VECTOR_STORE_ID:
                logger.error("OPENAI_VECTOR_STORE_ID environment variable not set")
                return {"error": "Vector store not configured. Please run scripts/upload-pdfs-to-openai.py and set OPENAI_VECTOR_STORE_ID in GitHub Secrets."}

            logger.info(f"Using pre-uploaded vector store: {OPENAI_VECTOR_STORE_ID}")

            # Create assistant with existing vector store (no file upload needed!)
            assistants = client.beta.assistants.create(
                name="ARFID Assistant",
                description="This tool assists medical professionals and patients with identifying food options for patients with ARFID.",
                instructions=instructions,
                model="o3-mini",
                tools=[{"type": "file_search"}],
                tool_resources={"file_search": {"vector_store_ids": [OPENAI_VECTOR_STORE_ID]}},
                response_format={
                            "type": "json_schema",
                            "json_schema": {
                                "name": "ARFID_Meal_Recommendations",
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "title": {
                                            "type": "string",
                                            "description": "The title of the meal recommendation schema."
                                        },
                                        "description": {
                                            "type": "string",
                                            "description": "A description of the purpose of the meal recommendations."
                                        },
                                        "recommendations": {
                                            "type": "array",
                                            "description": "A list of meal recommendations categorized by type.",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "category": {
                                                        "type": "string",
                                                        "description": "The category of the meal recommendations."
                                                    },
                                                    "foods": {
                                                        "type": "array",
                                                        "description": "A list of food items with their respective goals and transition strategies.",
                                                        "items": {
                                                            "type": "object",
                                                            "properties": {
                                                                "food": {
                                                                    "type": "string",
                                                                    "description": "The name of the food item."
                                                                },
                                                                "goal": {
                                                                    "type": "string",
                                                                    "description": "The intended goal of including this food item."
                                                                },
                                                                "transition_strategy": {
                                                                    "type": "string",
                                                                    "description": "A strategy for transitioning the patient to accept this food."
                                                                },
                                                                "allergy_considerations": {
                                                                    "type": "string",
                                                                    "description": "Precautions or considerations for the food item."
                                                                }
                                                            },
                                                            "required": [
                                                                "food",
                                                                "goal",
                                                                "transition_strategy",
                                                                "allergy_considerations"
                                                            ],
                                                            "additionalProperties": False
                                                        }
                                                    }
                                                },
                                                "required": [
                                                    "category",
                                                    "foods"
                                                ],
                                                "additionalProperties": False
                                            }
                                        },
                                        "notes": {
                                            "type": "array",
                                            "description": "Additional notes or remarks regarding the meal recommendations.",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "type": {
                                                        "type": "string",
                                                        "description": "The type of note (e.g., caution, encouragement)."
                                                    },
                                                    "content": {
                                                        "type": "string",
                                                        "description": "The content of the note."
                                                    }
                                                },
                                                "required": [
                                                    "type",
                                                    "content"
                                                ],
                                                "additionalProperties": False
                                            }
                                        },
                                        "recommendation_ease": {
                                            "type": "array",
                                            "description": "A list of recommendations with their ease of implementation.",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "recommendation": {
                                                        "type": "string",
                                                        "description": "The recommendation for the patient."
                                                    },
                                                    "ease": {
                                                        "type": "string",
                                                        "description": "An explanation of why the recommendation is easy to implement."
                                                    },
                                                    "accomplishment": {
                                                        "type": "string",
                                                        "description": "An explanation of what the recommendation accomplishes."
                                                    },
                                                    "preparation": {
                                                        "type": "string",
                                                        "description": "An explanation of how the recommendation can be prepared."
                                                    }
                                                },
                                                "required": [
                                                    "recommendation",
                                                    "ease",
                                                    "accomplishment",
                                                    "preparation"
                                                ],
                                                "additionalProperties": False
                                            }
                                        }
                                    },
                                    "required": [
                                        "title",
                                        "description",
                                        "recommendations",
                                        "notes",
                                        "recommendation_ease"
                                    ],
                                    "additionalProperties": False
                                },
                                "strict": True
                            }
                        },
                        reasoning_effort="medium"
                    )
                    
                    raw_assistant_id = assistants.id
                    hashed_key = hashlib.sha256(raw_assistant_id.encode("utf-8")).hexdigest()
                    redis_key = f"assistant:{hashed_key}"
                    redis_client.set(redis_key, raw_assistant_id)
                    logger.info(f"Assistant created with ID: {raw_assistant_id} (hashed as: {hashed_key})")
                    
                    return {"assistant_key": hashed_key, "status": "completed"}

    except Exception as e:
        logger.error(f"Error in setup_assistant_task: {str(e)}")
        return {"error": str(e)}

@app.route("/api/start", methods=["GET"])
def start():
    """Start assistant setup as a background task"""
    try:
        # Start the background task
        task = setup_assistant_task.apply_async()
        return jsonify({"task_id": task.id, "status": "started"}), 202
    except Exception as e:
        logger.error(f"Error starting assistant setup: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/start/status", methods=["POST"])
def get_start_status():
    """Check the status of the assistant setup task"""
    try:
        data = request.get_json()
        task_id = data.get("task_id")
        if not task_id:
            return jsonify({"error": "No task ID provided"}), 400

        task = AsyncResult(task_id, app=celery)
        
        if task.state == 'PENDING':
            response = {
                'state': task.state,
                'status': 'Setting up assistant...',
                'progress': 'Uploading files and creating assistant'
            }
        elif task.state == 'SUCCESS':
            result = task.result
            if isinstance(result, dict) and 'assistant_key' in result:
                response = {
                    'state': task.state,
                    'assistant_key': result['assistant_key'],
                    'status': 'Assistant ready'
                }
            else:
                response = {
                    'state': 'FAILURE',
                    'error': result.get('error', 'Unknown error')
                }
        else:
            response = {
                'state': task.state,
                'error': str(task.info) if task.info else 'Task failed'
            }
            
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error checking task status: {str(e)}")
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
            session["THREAD_ID"] = thread_id
            client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=f"Include these foods of patients {prompt1}"
            )
            client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=f"Do not include these foods patient doesn't like or eats: {prompt2}"
            )
            client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=f"Each recommendation should build on one of these foods {prompt1} or provide an alternative to one of these foods {prompt2}"
            )
            client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=f"Patient is allergic or has restrictions and can't eat: {prompt3}"
            ) 
        else: 
            thread_id = os.environ.get("THREAD_ID") or session.get("THREAD_ID")
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
            run = client.beta.threads.runs.create_and_poll(
              thread_id=thread_id, assistant_id=assistant_id, instructions=instructions,
              poll_interval_ms=10000
            )
            logger.info(f"Runs: {run}")
            logger.info(f"Run status: {run.status}")
            if run.status == "completed":
                logger.info(f"Run completed: {run}")
                messages =  client.beta.threads.messages.list(thread_id=thread_id)
                assistant_messages = []
                logger.info(f"Messages: {messages.data}")
                logger.info(f"Messages: {messages}")
                if len(messages.data) > 0:
                    for msg in messages.data:
                        if msg.role == "assistant":
                            logger.info(f"Assistant message: {msg}")
                            logger.info(f"Assistant role message: {msg.role}")
                            assistant_messages.append({ "role": msg.role, "content": msg.content })
                logger.info(f"Type Assistant messages: {type(assistant_messages)}")
                logger.info(f"Assistant messages: {assistant_messages}")
                if(len(assistant_messages) > 0):
                    return assistant_messages[0]["content"][0].text.value
                else:
                    return {"error": "No assistant messages found, please resubmit response"}, 500
                    
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
    thread_id = os.environ.get("THREAD_ID") or session.get("THREAD_ID")
    if not thread_id:
        return jsonify({"error": "Thread ID not found"}), 400
    client.beta.threads.messages.create(
        thread_id=thread_id, content=f"Updates from user: {update}", role="user"
    )
    client.beta.threads.messages.create(
        thread_id=thread_id, content=f"The user has provided the following recommendations: {recommendations}, please give more suggestions like that.", role="user"
    )
    client.beta.threads.messages.create(
        thread_id=thread_id, content="Please provide 20 recommendations in the same format as before.", role="user"
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
        