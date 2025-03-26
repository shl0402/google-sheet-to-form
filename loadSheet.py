import os
from app import Flask, render_template, request, jsonify
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from app import Flask, render_template, request, redirect, url_for, session
from google_auth_oauthlib.flow import Flow

app = Flask(__name__)

CLIENT_SECRETS_FILE = "client_secret_374818502051-20nosim2fh9d67680l0dta6e0nvtmg0i.apps.googleusercontent.com.json"
app.secret_key = 'your_dev_secret_key_here'

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/forms.body', 'https://www.googleapis.com/auth/spreadsheets.readonly']

CATEGORIES_TO_FILTER = ['Subject', 'Topic', 'Subtopic', 'Difficulty']

def get_credentials():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def fetch_sheet_data(sheet_url):
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    # Extract the spreadsheet ID from the URL
    sheet_id = sheet_url.split('/')[5]

    # Call the Sheets API
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range='A1:Z').execute()
    values = result.get('values', [])

    if not values:
        print('No data found.')
        return []

    return values

def extract_questions(data):
    headers = data[0]
    question_index = next((i for i, h in enumerate(headers) if h.lower() == 'question'), -1)
    question_id_index = next((i for i, h in enumerate(headers) if h.lower() == 'question id'), -1)
    answer_index = next((i for i, h in enumerate(headers) if h.lower() == 'correct answer'), -1)
    options_index = next((i for i, h in enumerate(headers) if h.lower() == 'answer options'), -1)

    if question_index == -1 or question_id_index == -1:
        print("Error: 'Question' or 'Question ID' column not found in the sheet.")
        return []

    questions = []
    for row in data[1:]:  # Skip the header row
        question_data = {}
        for i, header in enumerate(headers):
            if i < len(row):  # Check if the row has enough columns
                question_data[header.lower()] = row[i]
            else:
                question_data[header.lower()] = ''  # Add empty string if column is missing
        
        # Process options if present
        if options_index != -1 and options_index < len(row):
            options = row[options_index].split('||')
            question_data['options'] = [option.strip() for option in options if option.strip()]
        
        questions.append(question_data)

    return questions

def add_question_to_form(forms_service, form_id, question):
    try:
        if 'question' not in question or not question['question'].strip():
            return False, "Question text is missing"

        question_type = "TEXT" if 'options' not in question or not question['options'] else "MULTIPLE_CHOICE"
        
        if question_type == "MULTIPLE_CHOICE":
            options = question['options']
            
            new_question = {
                "requests": [{
                    "createItem": {
                        "item": {
                            "title": question['question'],
                            "questionItem": {
                                "question": {
                                    "required": False,
                                    "choiceQuestion": {
                                        "type": "RADIO",
                                        "options": [{"value": option} for option in options],
                                        "shuffle": False
                                    }
                                }
                            }
                        },
                        "location": {"index": 0}
                    }
                }]
            }
        else:
            new_question = {
                "requests": [{
                    "createItem": {
                        "item": {
                            "title": question['question'],
                            "questionItem": {
                                "question": {
                                    "required": False,
                                    "textQuestion": {}
                                }
                            }
                        },
                        "location": {"index": 0}
                    }
                }]
            }

        forms_service.forms().batchUpdate(formId=form_id, body=new_question).execute()
        return True, question_type
    except HttpError as error:
        return False, f"An error occurred: {error}"

@app.route('/')
def index():
    if 'credentials' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login')
def login():
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = url_for('oauth2callback', _external=True)
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = session['state']
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
    flow.redirect_uri = url_for('oauth2callback', _external=True)
    
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)
    
    credentials = flow.credentials
    session['credentials'] = credentials_to_dict(credentials)
    
    return redirect(url_for('index'))

@app.route('/get_questions', methods=['POST'])
def get_questions():
    sheet_url = request.json['sheetUrl']
    data = fetch_sheet_data(sheet_url)
    questions = extract_questions(data)
    return jsonify(questions)

@app.route('/generate_form', methods=['POST'])
def generate_form():
    selected_questions = request.json['selectedQuestions']
    form_title = request.json['formTitle']
    
    creds = get_credentials()
    forms_service = build('forms', 'v1', credentials=creds)

    # Create a new Google Form with the specified title
    NEW_FORM = {
        "info": {
            "title": form_title,
        }
    }
    result = forms_service.forms().create(body=NEW_FORM).execute()
    form_id = result['formId']
    form_url = f"https://docs.google.com/forms/d/{form_id}/edit"

    # Add selected questions to the form
    mc_success_list = []
    long_success_list = []
    error_list = []

    for question in selected_questions:
        success, result = add_question_to_form(forms_service, form_id, question)
        if success:
            if result == "MULTIPLE_CHOICE":
                mc_success_list.append(question['question id'])
            else:
                long_success_list.append(question['question id'])
        else:
            error_list.append((question['question id'], result))

    return jsonify({
        "formUrl": form_url,
        "mcSuccessList": mc_success_list,
        "longSuccessList": long_success_list,
        "errorList": error_list
    })

def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

if __name__ == '__main__':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # For development only
    app.run(debug=True)