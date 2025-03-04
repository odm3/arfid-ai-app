import azure.functions as func
import logging
import time
from openai import OpenAI
import os
from datetime import datetime, timedelta



OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
assistant_id = os.environ.get("ASSISTANT_ID")
instructions = """
You are an expert in Avoidant/Restrictive Food Intake Disorder. In order to broaden patients' diets, you use food chaining to create recommendations based on their safe products. You are particularly aware of their allergies, ensuring that you never make a recommendation that they are allergic to. When you receive a message, you'll respond with at least 20 options. Format the response based on the provided JSON Structure.

{
  "example_format": {
    "title": "ARFID Assistant",
    "description": "This tool assists medical professionals and patients with identifying food options for patients with ARFID.",
    "recommendations": [
      {
        "category": "Simple Carbohydrates",
        "foods": [
          {
            "food": "Example food",
            "ingredients": ["Example ingredient 1", "Example ingredient 2"],
            "goal": "Example goal for the food."
          }
        ]
      },
      {
        "category": "Simple Proteins",
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
        "content": "General goals of the recommendations."
      }
    ]
  }
}
"""

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
client = OpenAI(default_headers={"OpenAI-Beta": "assistants=v2"})

@app.route(route="create_message", methods=[func.HttpMethod.POST])
def create_message(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Python HTTP trigger function processed a request.")

    query = None
    try:
        data = req.get_json()
        prompt1 = data.get("patient_likes")
        prompt2 = data.get("patient_dislikes")
        prompt3 = data.get("patient_restrictions")
        initial = data.get("initial_request")
        update = data.get("update")
        if (initial and not prompt1 and not prompt2 and not prompt3) or (not initial and not update):
            return func.HttpResponse(
                "All inputs are required",
                status_code=400,
            )
        file = client.files.create(
            file=open("arfid.json", "rb"), purpose="assistants"
        )
        
        if initial:
            # Create a new thread for the first message
            thread = client.beta.threads.create(
                messages=[
                    {
                        "role": "user",
                        "content": "Create 20 simple recommendations for a patient with ARFID. Focus the recommendations on using 3 or less ingredients to broaden the patient's diet.",
                        "attachments": [
                            {
                                "file_id": file.id,
                                "tools": [{ "type": "code_interpreter"}]
                            }
                        ]
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
        return run_openai(client, thread_id)
    except Exception as e:
        return func.HttpResponse(
            body=str(e),
            status_code=500,
        )
        
    
def run_openai(client, thread_id):
    try:
        runs = client.beta.threads.runs.create(
            thread_id=thread_id, assistant_id=assistant_id, instructions=instructions
        )
        while True:
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=runs.id)
            if run.status == "completed":
                messages = client.beta.threads.messages.list(thread_id=thread_id)
                last_message = messages.data[0]
                return func.HttpResponse(body=last_message.content[0].text.value, status_code=200)
            time.sleep(5)
    except Exception as e:
        return func.HttpResponse(body=str(e), status_code=500)


@app.route(route="create_message2", auth_level=func.AuthLevel.ANONYMOUS, methods=[func.HttpMethod.POST])
def create_message2(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Python HTTP trigger function processed a request.")

    query = None
    try:
        data = req.get_json()
        prompt1 = data.get("patient_likes")
        prompt2 = data.get("patient_dislikes")
        prompt3 = data.get("patient_restrictions")
        initial = data.get("initial_request")
        update = data.get("update")
        if (initial and not prompt1 and not prompt2 and not prompt3) or (not initial and not update):
            return func.HttpResponse(
                "All inputs are required",
                status_code=400,
            )
        file = client.files.create(
            file=open("arfid.json", "rb"), purpose="assistants"
        )
        
        if initial:
            # Create a new thread for the first message
            thread = client.beta.threads.create(
                messages=[
                    {
                        "role": "user",
                        "content": "Create 20 simple recommendations for a patient with ARFID. Focus the recommendations on using 3 or less ingredients to broaden the patient's diet.",
                        "attachments": [
                            {
                                "file_id": file.id,
                                "tools": [{ "type": "code_interpreter"}]
                            }
                        ]
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
        return run_openai(client, thread_id)
    except Exception as e:
        return func.HttpResponse(
            body=str(e),
            status_code=500,
        )
        