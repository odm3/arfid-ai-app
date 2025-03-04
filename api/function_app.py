import azure.functions as func
import logging
import time
import openai
import os
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from datetime import datetime, timedelta

credential = DefaultAzureCredential()
key_vault_name = os.environ.get("KEY_VAULT_NAME")
key_vault_url = f"https://{key_vault_name}.vault.azure.net"
secret_client = SecretClient(vault_url=key_vault_url, credential=credential)
OPENAI_API_KEY = secret_client.get_secret("OPENAI-API-KEY").value
assistant_id = secret_client.get_secret("assistant-id").value
instructions = """
You are an expert in Avoidant/Restrictive Food Intake Disorder. In order to broaden patients' diets, you use food chaining to create recommendations based on their safe products. You are particularly aware of their allergies, ensuring that you never make a recommendation that they are allergic to. When you receive a message, you'll respond with at least 20 options. Format the response based on the provided JSON Structure.

{
  "example_format": {
    "title": "ARFID Assistant",
    "description": "This tool assists medical professionals and patients with identifying food options for patients with ARFID.",
    "recommendations": [
      {
        "category": "simple_carbohydrates",
        "foods": [
          {
            "food": "Example food",
            "ingredients": ["Example ingredient 1", "Example ingredient 2"],
            "goal": "Example goal for the food."
          }
        ]
      },
      {
        "category": "simple_proteins",
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
client = openai.OpenAI()

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
            file=open("api/arfid.json", "rb"), purpose="assistants"
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
            expiration_time = datetime.now(datetime.timezone.utc) + timedelta(hours=1)
            secret_client.set_secret(
                name=f"thread-id-{thread.id}-{expiration_time}",
                value=thread.id,
                expires_on=expiration_time
            )
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
            thread_id_secret = secret_client.get_secret(f"thread-id-{thread_id}")
            thread_id = thread_id_secret.value
            query = client.beta.threads.messages.create(
                thread_id=thread_id, content=update, role="user"
            )
        return run_openai(client, thread_id)
    except Exception as e:
        return func.HttpResponse(
            {"error": str(e)},
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
                return func.HttpResponse({"message": last_message.content[0].text.value}, status_code=200)
            time.sleep(5)
    except Exception as e:
        return func.HttpResponse({"error": str(e)}, status_code=500)

