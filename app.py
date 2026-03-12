from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
import os
import json
import uuid
from datetime import datetime, timedelta
import google.genai as genai
from werkzeug.utils import secure_filename
from openai import OpenAI
import anthropic

app = Flask(__name__)
app.secret_key = 'odorico-secret-key-change-in-production'

# Configure Flask to use Django-like template syntax
app.jinja_env.variable_start_string = '{{'
app.jinja_env.variable_end_string = '}}'
app.jinja_env.comment_start_string = '{#'
app.jinja_env.comment_end_string = '#}'
app.jinja_env.line_statement_prefix = '#'
app.jinja_env.line_comment_prefix = '##'

# Session security configuration
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Models by provider
MODELS = {
    'gemini': {
        'gemini-2.0-flash-lite': 'Gemini 2.0 Flash‑Lite',
        'gemini-2.0-flash': 'Gemini 2.0 Flash',
        'gemini-3.1-flash-lite-preview': 'Gemini 3.1 Flash‑Lite',
        'gemini-2.0-pro': 'Gemini 2.0 Pro'
    },
    'openai': {
        'gpt-5-nano': 'GPT‑5 nano',
        'gpt-5-mini': 'GPT‑5 mini',
        'o4-mini': 'o4‑mini',
        'gpt-5.4': 'GPT‑5.4',
        'o1': 'o1'
    },
    'anthropic': {
        'claude-haiku-4.5': 'Claude Haiku 4.5',
        'claude-sonnet-4.6': 'Claude Sonnet 4.6',
        'claude-opus-4.5': 'Claude Opus 4.5'
    }
}

# Agent storage file
AGENTS_FILE = 'config/agents.json'
# API keys storage file
API_KEYS_FILE = 'config/api_keys.json'

# Session-based API key management
def get_api_keys():
    """Get API keys from session"""
    return {
        'gemini': session.get('gemini_key', ''),
        'openai': session.get('openai_key', ''),
        'anthropic': session.get('anthropic_key', '')
    }

def set_api_key(provider, api_key):
    """Set API key in session"""
    session[f'{provider}_key'] = api_key

def clear_api_keys():
    """Clear all API keys from session"""
    for provider in ['gemini', 'openai', 'anthropic']:
        session.pop(f'{provider}_key', None)

def test_api_key(provider, api_key):
    """Test if an API key is valid"""
    try:
        if provider == 'gemini':
            client = genai.Client(api_key=api_key)
            # Test with chat-based approach
            chat = client.chats.create(model='gemini-2.0-flash')
            response = chat.send_message('Hello')
            return True, 'API key is valid'
        elif provider == 'openai':
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model='gpt-3.5-turbo',
                messages=[{'role': 'user', 'content': 'Hello'}],
                max_tokens=1
            )
            return True, 'API key is valid'
        elif provider == 'anthropic':
            # Configure Anthropic
            anthropic_client = anthropic.Anthropic(api_key=api_key)
            
            # Build messages
            messages = []
            if agent['prompt']:
                messages.append({'role': 'user', 'content': agent['prompt']})
                messages.append({'role': 'assistant', 'content': 'I understand. I will act according to these instructions.'})
            messages.append({'role': 'user', 'content': user_message})
            
            response = anthropic_client.messages.create(
                model=agent['model'],
                max_tokens=2000,
                messages=messages
            )
            
            return jsonify({
                'response': response.content[0].text,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return False, 'Unknown provider'
    except Exception as e:
        return False, f'Invalid API key: {str(e)}'

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

@app.route('/api_keys', methods=['GET', 'POST'])
def manage_api_keys():
    """Manage API keys for all providers"""
    if request.method == 'POST':
        # Update API keys from form
        for provider in ['gemini', 'openai', 'anthropic']:
            api_key = request.form.get(f'{provider}_key', '').strip()
            set_api_key(provider, api_key)
        
        flash('API keys have been updated for this session!')
        return redirect(url_for('manage_api_keys'))
    
    # GET request
    api_keys = get_api_keys()
    return render_template('api_keys.html', api_keys=api_keys, models=MODELS)

@app.route('/test_api_key/<provider>', methods=['POST'])
def test_api_key_route(provider):
    """Test API key for a specific provider"""
    api_keys = get_api_keys()
    api_key = api_keys.get(provider, '')
    
    if not api_key:
        return jsonify({'success': False, 'message': 'No API key configured'})
    
    is_valid, message = test_api_key(provider, api_key)
    return jsonify({'success': is_valid, 'message': message})

@app.route('/clear_api_keys', methods=['POST'])
def clear_api_keys_route():
    """Clear all API keys from session"""
    clear_api_keys()
    flash('All API keys have been cleared from this session.')
    return redirect(url_for('manage_api_keys'))

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
        provider = request.form.get('provider')
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
            'provider': provider,
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
    
    return render_template('configure.html', agent=agent, models=MODELS, agent_id=agent_id)

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
    
    # Get API key for the provider
    api_keys = get_api_keys()
    provider = agent.get('provider', 'gemini')
    api_key = api_keys.get(provider, '')
    
    if not api_key:
        return jsonify({'error': f'{provider.title()} API key not configured'}), 500
    
    try:
        if provider == 'gemini':
            # Configure Gemini
            gemini_client = genai.Client(api_key=api_key)
            chat = gemini_client.chats.create(model=agent['model'])
            
            # Send the agent prompt first if it exists
            if agent['prompt']:
                chat.send_message(agent['prompt'])
            
            # Send the user message and get response
            response = chat.send_message(user_message)
            
            return jsonify({
                'response': response.text,
                'timestamp': datetime.now().isoformat()
            })
        elif provider == 'openai':
            # Configure OpenAI
            openai_client = OpenAI(api_key=api_key)
            
            # Build messages
            messages = []
            if agent['prompt']:
                messages.append({'role': 'system', 'content': agent['prompt']})
            messages.append({'role': 'user', 'content': user_message})
            
            response = openai_client.chat.completions.create(
                model=agent['model'],
                messages=messages,
                max_tokens=2000
            )
            
            return jsonify({
                'response': response.choices[0].message.content,
                'timestamp': datetime.now().isoformat()
            })
            
        elif provider == 'anthropic':
            # Configure Anthropic
            anthropic_client = anthropic.Anthropic(api_key=api_key)
            
            # Build messages
            messages = []
            if agent['prompt']:
                messages.append({'role': 'user', 'content': agent['prompt']})
                messages.append({'role': 'assistant', 'content': 'I understand. I will act according to these instructions.'})
            messages.append({'role': 'user', 'content': user_message})
            
            response = anthropic_client.messages.create(
                model=agent['model'],
                max_tokens=2000,
                messages=messages
            )
            
            return jsonify({
                'response': response.content[0].text,
                'timestamp': datetime.now().isoformat()
            })
        
        else:
            return jsonify({'error': f'Unknown provider: {provider}'}), 500
            
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
        'provider': agent.get('provider', 'gemini'),
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
