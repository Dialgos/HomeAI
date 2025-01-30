from flask import Flask, request, jsonify
from openai import OpenAI
import os
import json
from threading import Thread
from uuid import uuid4
import constants

app = Flask(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=constants.OpenAIAPIKey)

MESSAGES_FOLDER = 'Messages'
if not os.path.exists(MESSAGES_FOLDER):
    os.makedirs(MESSAGES_FOLDER)

message_status = {}  # To track status and file path for each message ID

def process_request(model, prompt, system_prompt, request_id):
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    )

    # Extract the JSON serializable part of the completion
    completion_data = {
        'id': completion.id,
        'object': completion.object,
        'created': completion.created,
        'model': completion.model,
        'choices': [choice.to_dict() for choice in completion.choices]  # Convert choices to dict
    }

    response_filename = os.path.join(MESSAGES_FOLDER, f"response_{request_id}.json")
    with open(response_filename, 'w') as f:
        json.dump(completion_data, f, indent=4)

    message_status[request_id] = {'status': 'completed', 'file_path': response_filename}

    print(f"Notification: The response for message ID {request_id} is ready.")


@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    model = data.get('model')
    prompt = data.get('prompt')
    system_prompt = data.get('system_prompt', "")

    if not all([model, prompt]):
        return jsonify({'error': 'Missing required parameters: model, prompt'}), 400

    request_id = str(uuid4())  # Generate a unique ID for this request
    message_status[request_id] = {'status': 'processing'}

    thread = Thread(target=process_request, args=(model, prompt, system_prompt, request_id))
    thread.start()

    return jsonify({'message': 'Request received. Processing...', 'request_id': request_id}), 200

@app.route('/api/status/<request_id>', methods=['GET'])
def check_status(request_id):
    status_info = message_status.get(request_id)
    if not status_info:
        return jsonify({'error': 'Invalid request ID'}), 404

    return jsonify({'status': status_info['status']}), 200

@app.route('/api/retrieve/<request_id>', methods=['GET'])
def retrieve_message(request_id):
    status_info = message_status.get(request_id)
    if not status_info or status_info['status'] != 'completed':
        return jsonify({'error': 'Message not available or still processing'}), 404

    with open(status_info['file_path'], 'r') as f:
        response_data = json.load(f)

    return jsonify(response_data), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
