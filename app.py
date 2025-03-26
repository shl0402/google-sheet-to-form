from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sys
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import re
import logging
from dateutil import parser
import json
from datetime import datetime, timezone
import traceback
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # for flash messages

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/forms.body', 'https://www.googleapis.com/auth/spreadsheets.readonly']
CLIENT_SECRETS_FILE = "client_secret_374818502051-20nosim2fh9d67680l0dta6e0nvtmg0i.apps.googleusercontent.com.json"

# Use this function to get the current UTC time
def get_current_utc_time():
    return datetime.now(timezone.utc)

# When creating datetime objects from user input or database, make them UTC aware
def make_utc_aware(naive_datetime):
    return naive_datetime.replace(tzinfo=timezone.utc)

def get_credentials():
    creds = None
    if os.path.exists('token.json'):
        with open('token.json', 'r') as token_file:
            token_data = json.load(token_file)
            expiry = parser.parse(token_data.get('expiry', ''))
            # Make the expiry timezone-aware
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            
            # Compare with timezone-aware current time
            if expiry > datetime.now(timezone.utc):
                creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            else:
                os.remove('token.json')
                print("Token has expired. Removing token.json and requesting new credentials.")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the new credentials
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return creds

def extract_sheet_id(sheet_url):
    # Regular expression to match Google Sheets URL patterns
    pattern = r'/spreadsheets/d/([a-zA-Z0-9-_]+)'
    match = re.search(pattern, sheet_url)
    if match:
        return match.group(1)
    return None

def is_valid_sheet_url(sheet_url):
    try:
        creds = get_credentials()
        service = build('sheets', 'v4', credentials=creds)
        
        sheet_id = extract_sheet_id(sheet_url)
        if not sheet_id:
            return False
        
        # Try to fetch metadata (this will fail if the URL is invalid)
        sheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        return True
    except HttpError:
        return False
    
def fetch_sheet_data(sheet_url):
    logger.info(f"Fetching data from sheet: {sheet_url}")
    try:
        creds = get_credentials()
        service = build('sheets', 'v4', credentials=creds)

        sheet_id = extract_sheet_id(sheet_url)
        if not sheet_id:
            logger.error("Failed to extract sheet ID")
            return []

        logger.debug(f"Fetching data for sheet ID: {sheet_id}")
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=sheet_id, range='A1:Z').execute()
        values = result.get('values', [])

        if not values:
            logger.warning('No data found in the sheet.')
            return []

        logger.info(f"Successfully fetched {len(values)} rows of data")
        return values
    except HttpError as error:
        logger.error(f"HTTP error occurred while fetching sheet data: {error}")
        return []
    except Exception as e:
        logger.exception(f"Unexpected error fetching sheet data: {e}")
        return []

def create_category_hierarchy(data):
    headers = data[0]
    subject_index = next((i for i, h in enumerate(headers) if h.lower() == 'subject'), -1)
    topic_index = next((i for i, h in enumerate(headers) if h.lower() == 'topic'), -1)
    subtopic_index = next((i for i, h in enumerate(headers) if h.lower() == 'subtopic'), -1)

    category_hierarchy = {
        'subjects': set(),
        'topics': set(),
        'subtopics': set(),
        'subject_to_topic': {},
        'topic_to_subtopic': {}
    }

    for row in data[1:]:
        subject = row[subject_index].lower()
        topic = row[topic_index].lower()
        subtopic = row[subtopic_index].lower()

        category_hierarchy['subjects'].add(subject)
        category_hierarchy['topics'].add(topic)
        category_hierarchy['subtopics'].add(subtopic)

        if subject not in category_hierarchy['subject_to_topic']:
            category_hierarchy['subject_to_topic'][subject] = set()
        category_hierarchy['subject_to_topic'][subject].add(topic)

        if topic not in category_hierarchy['topic_to_subtopic']:
            category_hierarchy['topic_to_subtopic'][topic] = set()
        category_hierarchy['topic_to_subtopic'][topic].add(subtopic)

    return category_hierarchy

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
        if options_index != -1 and options_index < len(row) and row[options_index].strip():
            options = row[options_index].split('||')
            question_data['options'] = [option.strip() for option in options if option.strip()]
        
        # Process correct answer
        if answer_index != -1 and answer_index < len(row):
            correct_answer = row[answer_index].strip()
            question_data['correct_answer'] = correct_answer
            
            # Check if the correct answer is in the options
            if 'options' in question_data and correct_answer not in question_data['options']:
                print(f"Warning: Correct answer '{correct_answer}' not found in options for question: {question_data.get('question', 'Unknown')}")
        
        questions.append(question_data)

    return questions

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        sheet_url = request.form.get('sheetUrl')
        if is_valid_sheet_url(sheet_url):
            print(f"Valid Sheet URL: {sheet_url}", file=sys.stderr)

            # Fetch Google Sheet data
            data = fetch_sheet_data(sheet_url)

            # Extract questions with their categories
            questionsList = extract_questions(data)

            # Print some information
            print("Google Sheet data loaded successfully.")
            print(f"Number of rows: {len(data)}")
            print(f"Number of columns: {len(data[0])}")

            # Print questions with their categories
            print("\nQuestions with categories:")
            for i, question in enumerate(questionsList, 1):
                print(f"\nQuestion {i} (ID: {question.get('question id', 'N/A')}):")
                for category, value in question.items():
                    if category != 'options':
                        print(f"  {category}: {value}")
                if 'options' in question:
                    print(f"  Options: {', '.join(question['options'])}")

            # Store questionsList in session or pass it to the template
            session['questionsList'] = questionsList

            # Redirect to questions page
            return jsonify(success=True, redirect=url_for('questions'))
        else:
            print(f"Invalid Sheet URL: {sheet_url}", file=sys.stderr)
            return jsonify(success=False, message="Invalid URL given. Please check and try again.")

    return render_template('index.html')

@app.route('/questions')
def questions():
    questionsList = session.get('questionsList', [])
    return render_template('questions.html', questions=questionsList)

def add_question_to_form(forms_service, form_id, question):
    try:
        app.logger.info(f"Adding question to form {form_id}: {question['question'][:50]}...")
        app.logger.debug(f"Full question data: {question}")

        if 'question' not in question or not question['question'].strip():
            app.logger.warning("Question text is missing")
            return False, "Question text is missing"

        question_type = "TEXT" if 'options' not in question or not question['options'] else "MULTIPLE_CHOICE"
        app.logger.info(f"Question type: {question_type}")
        
        if question_type == "MULTIPLE_CHOICE":
            options = question.get('options', '').split('||')
            options = [option.strip() for option in options if option.strip()]  # Remove empty options
            correct_answer = question.get('correctAnswer', '')
            
            app.logger.debug(f"Options: {options}")
            app.logger.debug(f"Correct answer: {correct_answer}")
            
            if not options:
                app.logger.warning("No valid options provided for multiple-choice question")
                return False, "No valid options provided for multiple-choice question"
            
            if correct_answer not in options:
                app.logger.warning("Correct answer is not in the options")
                return False, "Correct answer is not in the options"
            
            options = list(dict.fromkeys(options))
            
            new_question = {
                "requests": [{
                    "createItem": {
                        "item": {
                            "title": question['question'],
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "grading": {
                                        "pointValue": 1,
                                        "correctAnswers": {
                                            "answers": [{"value": correct_answer}]
                                        },
                                        "whenRight": {"text": "Correct!"},
                                        "whenWrong": {"text": "Sorry, that's incorrect."}
                                    },
                                    "choiceQuestion": {
                                        "type": "RADIO",
                                        "options": [{"value": option.strip()} for option in options],
                                        "shuffle": False
                                    }
                                }
                            },
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
                                    "required": True,
                                    "textQuestion": {
                                        "paragraph": True
                                    }
                                }
                            }
                        },
                        "location": {"index": 0}
                    }
                }]
            }

        app.logger.debug(f"Sending request to create question: {new_question}")
        response = forms_service.forms().batchUpdate(formId=form_id, body=new_question).execute()
        app.logger.debug(f"Received response: {response}")
        
        if 'replies' in response and response['replies']:
            reply = response['replies'][0]
            if 'createItem' in reply:
                create_item = reply['createItem']
                if 'questionId' in create_item:
                    question_id = create_item['questionId'][0]  # The questionId is now an array
                    app.logger.info(f"Question added successfully with ID: {question_id}")
                    return True, question_type
                else:
                    app.logger.warning("Question ID not found in response")
                    return False, "Question ID not found in response"
            else:
                app.logger.warning("CreateItem not found in response")
                return False, "CreateItem not found in response"
        else:
            app.logger.warning("Replies not found in response")
            return False, "Replies not found in response"

    except HttpError as error:
        app.logger.error(f"An HTTP error occurred: {error}")
        return False, f"An error occurred: {error}"
    except Exception as e:
        app.logger.error(f"An unexpected error occurred: {str(e)}")
        app.logger.error(traceback.format_exc())
        return False, f"An unexpected error occurred: {str(e)}"


@app.route('/generate_form', methods=['POST'])
def generate_form():
    try:
        app.logger.info("Received request to generate form")
        data = request.json
        app.logger.debug(f"Received data: {data}")
        selected_questions = data.get('selected_questions', [])
        form_title = data.get('formTitle', 'New Quiz Form')

        app.logger.info(f"Creating form with title: {form_title}")
        app.logger.info(f"Number of selected questions: {len(selected_questions)}")

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
        app.logger.info(f"Created new form with ID: {form_id}")

        # Generate the edit URL
        form_edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
        
        # Print the edit URL to the console
        print(f"Form edit URL: {form_edit_url}")
        app.logger.info(f"Form edit URL: {form_edit_url}")

        # Update the form to be a quiz
        update_request = {
            "requests": [
                {
                    "updateSettings": {
                        "settings": {
                            "quizSettings": {
                                "isQuiz": True
                            }
                        },
                        "updateMask": "quizSettings.isQuiz"
                    }
                }
            ]
        }
        forms_service.forms().batchUpdate(formId=form_id, body=update_request).execute()
        app.logger.info("Updated form to be a quiz")

        form_url = f"https://docs.google.com/forms/d/{form_id}/edit"

        # Add selected questions to the form
        mc_success_list = []
        long_success_list = []
        error_list = []
                    
        for question in selected_questions:
            app.logger.info(f"Adding question: {question['question'][:50]}...")
            success, result = add_question_to_form(forms_service, form_id, question)
            if success:
                app.logger.info(f"Successfully added question as {result}")
                if result == "MULTIPLE_CHOICE":
                    mc_success_list.append(question['questionId'])
                else:
                    long_success_list.append(question['questionId'])
            else:
                app.logger.error(f"Failed to add question: {result}")
                error_list.append((question['questionId'], result))

        # Prepare response
        response = {
            "formId": form_id,
            "formUrl": form_url,
            "multipleChoiceQuestions": [{"id": qid, "type": "Multiple Choice"} for qid in mc_success_list],
            "longAnswerQuestions": [{"id": qid, "type": "Long Answer"} for qid in long_success_list],
            "errors": [{"questionId": qid, "error": error} for qid, error in error_list],
            "totalAdded": len(mc_success_list) + len(long_success_list),
            "totalErrors": len(error_list),
            "success": True
        }

        app.logger.info(f"Form generation complete. Total added: {response['totalAdded']}, Total errors: {response['totalErrors']}")
        app.logger.info(f"MC: {mc_success_list}")
        app.logger.info(f"LQ: {long_success_list}")
        app.logger.info(f"Error: {error_list}")
        return jsonify(response), 200

    except Exception as e:
        app.logger.error(f"An error occurred: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    # Log the error
    app.logger.error(f"Unhandled exception: {str(e)}")
    # Flash a user-friendly message
    flash("An error occurred. Please try again.", "error")
    # Redirect to the index page
    return redirect(url_for('index'))

if __name__ == '__main__':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # To allow OAuth2 to work on localhost
    app.run(debug=True)