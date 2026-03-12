from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
import os
import json
import uuid
from datetime import datetime
import google.generativeai as genai
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'odorico-secret-key-change-in-production'

# Configure Flask to use Django-like template syntax
app.jinja_env.variable_start_string = '{{'
app.jinja_env.variable_end_string = '}}'
app.jinja_env.comment_start_string = '{#'
app.jinja_env.comment_end_string = '#}'
app.jinja_env.line_statement_prefix = '#'
app.jinja_env.line_comment_prefix = '##'

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Gemini models
GEMINI_MODELS = {
    'gemini-2.0-flash': 'Gemini 2.0 Flash',
    'gemini-2.0-flash-lite': 'Gemini 2.0 Flash‑Lite',
    'gemini-2.0-pro': 'Gemini 2.0 Pro',
    'gemini-3.1-flash-lite-preview': 'Gemini 3.1 Flash‑Lite'
}

# Agent storage file
AGENTS_FILE = 'config/agents.json'

def load_api_key():
    """Load Gemini API key from config file"""
    try:
        with open('config/api_key.txt', 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def load_agents():
    """Load agents from JSON file"""
    try:
        with open(AGENTS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_agents(agents):
    """Save agents to JSON file"""
    os.makedirs('config', exist_ok=True)
    with open(AGENTS_FILE, 'w') as f:
        json.dump(agents, f, indent=2)

def allowed_file(filename):
    """Check if file has allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Main page with agent selection"""
    agents = load_agents()
    return render_template('index.html', agents=agents)

@app.route('/configure', methods=['GET', 'POST'])
def configure_agent():
    """Configure a new or existing agent"""
    if request.method == 'POST':
        agent_id = request.form.get('agent_id') or str(uuid.uuid4())
        name = request.form.get('name', '').strip()
        model = request.form.get('model')
        prompt_text = request.form.get('prompt_text', '').strip()
        
        # Handle file upload
        file_prompt = ''
        if 'prompt_file' in request.files:
            file = request.files['prompt_file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                with open(filepath, 'r', encoding='utf-8') as f:
                    file_prompt = f.read()
                os.remove(filepath)  # Clean up uploaded file
        
        # Merge prompts (file content first, then text content)
        combined_prompt = file_prompt
        if prompt_text:
            if combined_prompt:
                combined_prompt += '\n\n' + prompt_text
            else:
                combined_prompt = prompt_text
        
        agents = load_agents()
        agents[agent_id] = {
            'name': name,
            'model': model,
            'prompt': combined_prompt,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        save_agents(agents)
        flash(f'Agent "{name}" has been saved successfully!')
        return redirect(url_for('index'))
    
    # GET request - show configuration form
    agent_id = request.args.get('agent_id')
    agent = None
    if agent_id:
        agents = load_agents()
        agent = agents.get(agent_id)
    
    return render_template('configure.html', agent=agent, models=GEMINI_MODELS, agent_id=agent_id)

@app.route('/delete_agent/<agent_id>')
def delete_agent(agent_id):
    """Delete an agent"""
    agents = load_agents()
    if agent_id in agents:
        agent_name = agents[agent_id]['name']
        del agents[agent_id]
        save_agents(agents)
        flash(f'Agent "{agent_name}" has been deleted.')
    return redirect(url_for('index'))

@app.route('/chat/<agent_id>')
def chat_page(agent_id):
    """Chat page for a specific agent"""
    agents = load_agents()
    agent = agents.get(agent_id)
    if not agent:
        flash('Agent not found!')
        return redirect(url_for('index'))
    
    return render_template('chat.html', agent=agent, agent_id=agent_id)

@app.route('/chat/<agent_id>/send', methods=['POST'])
def send_message(agent_id):
    """Send message to agent and get response"""
    agents = load_agents()
    agent = agents.get(agent_id)
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404
    
    user_message = request.json.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    # Get API key
    api_key = load_api_key()
    if not api_key:
        return jsonify({'error': 'Gemini API key not configured'}), 500
    
    try:
        # Configure Gemini
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(agent['model'])
        
        # Start chat with agent prompt
        chat = model.start_chat(history=[])
        
        # Send agent prompt first
        if agent['prompt']:
            chat.send_message(agent['prompt'])
        
        # Send user message and get response
        response = chat.send_message(user_message)
        
        return jsonify({
            'response': response.text,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get response: {str(e)}'}), 500

@app.route('/export/<agent_id>')
def export_conversation(agent_id):
    """Export conversation history"""
    agents = load_agents()
    agent = agents.get(agent_id)
    if not agent:
        flash('Agent not found!')
        return redirect(url_for('index'))
    
    # For now, create a simple export file
    # In a real implementation, you'd store conversation history
    export_data = {
        'agent_name': agent['name'],
        'model': agent['model'],
        'prompt': agent['prompt'],
        'exported_at': datetime.now().isoformat(),
        'conversation': []  # Would contain actual conversation history
    }
    
    filename = f"conversation_{agent['name']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    return send_file(filepath, as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
