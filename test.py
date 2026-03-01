import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY")) #On a hidden .env file if you need it let me know

response = client.models.generate_content(
    model="gemini-2.5-flash", #Has to be this model bc it doesnt allow 2.0
    contents="Say hello and tell me you are ready to help identify musical notes!"  #Confirm activation and stuff
)

print(response.text)