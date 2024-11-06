from openai import OpenAI
import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import base64
load_dotenv()

app = FastAPI()

class OpenAIClient:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def transcribe_audio(self, file_path: str, model: str = "whisper-1") -> str:
        with open(file_path, "rb") as audio_file:
            transcription = self.client.audio.transcriptions.create(
                model=model,
                file=audio_file,
            )
        return transcription.text

    def extract_meeting_details(self, input_text: str) -> dict:
        prompt = f"""
        Extract the meeting details in JSON format from the following input text:
        
        Input: "{input_text}"
        
        The JSON output should have two fields:
        - "duration_minutes": the duration of the meeting in minutes
        - "start_timestamp": the timestamp of when the meeting starts in ISO 8601 format
        
        Example output:
        {{
            "duration_minutes": 30,
            "start_timestamp": "2024-12-26T12:00:00+05:30"
        }}
        """
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "meeting_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "duration_minutes": {"description": "Duration in minutes", "type": "integer"},
                        "start_timestamp": {"description": "Start timestamp in ISO 8601", "type": "string"}
                    },
                    "additionalProperties": False
                }
            }
        }
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format=response_format,
            max_tokens=50,
            temperature=0
        )
        json_output = json.loads(response.choices[0].message.content)
        return json_output

class ZoomAPI:
    def __init__(self, client_id: str, client_secret: str, account_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_id = account_id
        self.token = self.generate_token()

    def generate_token(self) -> str:
        base64_credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode("ascii")
        url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={self.account_id}"
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {base64_credentials}"
        }
        
        response = requests.post(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print("Access Token:", data.get("access_token"))
            return data.get("access_token")
        else:
            print("Error:", response.json())
            response.raise_for_status()  

    def create_zoom_meeting(self, start_timestamp: str, duration: int) -> dict:
        url = "https://api.zoom.us/v2/users/me/meetings"
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        data = {
            "topic": "Zoom meeting for something",
            "type": 2, 
            "start_time": start_timestamp,
            "duration": duration
        }
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 201:
            return response.json()
        else:
            raise HTTPException(status_code=response.status_code, detail=response.json())

class AudioFile(BaseModel):
    file_path: str

@app.post("/create_zoom_meeting/")
async def create_zoom_meeting_endpoint(audio: AudioFile):
    try:
        openai_client = OpenAIClient(api_key=os.getenv("API_KEY"))
        print(openai_client)
        zoom_client = ZoomAPI(
            client_id=os.getenv("ZOOM_CLIENT_ID"),
            client_secret=os.getenv("ZOOM_CLIENT_SECRET"),
            account_id=os.getenv("ZOOM_ACCOUNT_ID")
        )

        transcription_text = openai_client.transcribe_audio(audio.file_path)
        print(transcription_text)
        meeting_details = openai_client.extract_meeting_details(transcription_text)
        print(meeting_details)

        zoom_meeting = zoom_client.create_zoom_meeting(
            start_timestamp=meeting_details["start_timestamp"],
            duration=meeting_details["duration_minutes"]
        )
        print(zoom_meeting)

        return {"status": "Success", "zoom_meeting": zoom_meeting}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
