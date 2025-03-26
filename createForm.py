import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/forms.body']

def get_credentials():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret_374818502051-20nosim2fh9d67680l0dta6e0nvtmg0i.apps.googleusercontent.com.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def main():
    creds = get_credentials()
    service = build('forms', 'v1', credentials=creds)

    # Example: Create a new form
    NEW_FORM = {
        "info": {
            "title": "My Test Form",
        }
    }
    result = service.forms().create(body=NEW_FORM).execute()
    print(f"Created form with ID: {result['formId']}")

if __name__ == '__main__':
    main()