from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
import os
import json
import uuid
from datetime import datetime, timedelta
import google.genai as genai
from werkzeug.utils import secure_filename
from openai import OpenAI
import anthropic
from external_tools import ExternalToolManager, AgentCommunicator

app = Flask(__name__)

# Configure secret key from environment variable for production
app.secret_key = os.environ.get('SECRET_KEY', 'odorico-secret-key-change-in-production')

# Configure Flask to use Django-like template syntax
app.jinja_env.variable_start_string = '{{'
app.jinja_env.variable_end_string = '}}'
app.jinja_env.comment_start_string = '{#'
app.jinja_env.comment_end_string = '#}'
app.jinja_env.line_statement_prefix = '#'
app.jinja_env.line_comment_prefix = '##'

# Session security configuration
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
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

# Session-based API key management with environment variable support
def get_api_keys():
    """Get API keys from session and environment variables"""
    # Priority: Environment variables > Session variables
    return {
        'gemini': os.environ.get('GOOGLE_API_KEY') or session.get('gemini_key', ''),
        'openai': os.environ.get('OPENAI_API_KEY') or session.get('openai_key', ''),
        'anthropic': os.environ.get('ANTHROPIC_API_KEY') or session.get('anthropic_key', ''),
        # External tools for Oracle
        'searchapi': os.environ.get('SEARCHAPI_API_KEY'),
        'linkedin': os.environ.get('LINKEDIN_API_KEY'),
        'meta': os.environ.get('META_API_KEY')
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
            chat = client.chats.create(model='gemini-3.1-flash-lite-preview')
            response = chat.send_message('Hello')
            return True, 'API key is valid'
        elif provider == 'openai':
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model='gpt-5-nano',
                messages=[{'role': 'user', 'content': 'Hello'}],
                max_tokens=1
            )
            return True, 'API key is valid'
        elif provider == 'anthropic':
            # Configure Anthropic
            anthropic_client = anthropic.Anthropic(api_key=api_key)
            # Test with a simple message to validate the API key (fixed model)
            response = anthropic_client.messages.create(
                model='claude-haiku-4.5',
                messages=[{'role': 'user', 'content': 'Hello'}],
                max_tokens=1
            )
            return True, 'API key is valid'
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
        # Update API keys from form (only update session, not environment)
        for provider in ['gemini', 'openai', 'anthropic']:
            api_key = request.form.get(f'{provider}_key', '').strip()
            set_api_key(provider, api_key)
        
        flash('API keys have been updated for this session!')
        return redirect(url_for('manage_api_keys'))
    
    # GET request
    api_keys = get_api_keys()
    
    # Determine source of each key (environment vs session)
    api_key_sources = {}
    for provider, key in api_keys.items():
        if provider in ['searchapi', 'linkedin', 'meta']:
            # External tools only come from environment
            api_key_sources[provider] = {
                'key': key or '',
                'source': 'environment' if key else 'not_configured',
                'editable': False
            }
        else:
            # Main providers can come from environment or session
            env_key = os.environ.get(f'{provider.upper()}_API_KEY' if provider != 'gemini' else 'GOOGLE_API_KEY')
            if env_key:
                api_key_sources[provider] = {
                    'key': env_key[:10] + '...' if len(env_key) > 10 else env_key,
                    'source': 'environment',
                    'editable': False
                }
            else:
                session_key = session.get(f'{provider}_key', '')
                api_key_sources[provider] = {
                    'key': session_key,
                    'source': 'session' if session_key else 'not_configured',
                    'editable': True
                }
    
    return render_template('api_keys.html', api_keys=api_key_sources, models=MODELS)

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
        
        # Check if this is the Oracle agent
        is_oracle = agent_id == 'oracle-agent'
        
        if is_oracle:
            # Oracle agent: only allow model changes
            name = "Oracle"  # Fixed name
            provider = "gemini"  # Fixed provider
            model = request.form.get('model', 'gemini-3.1-flash-lite-preview')
            # Oracle prompt is fixed, don't change it
            agents = load_agents()
            oracle_prompt = agents.get('oracle-agent', {}).get('prompt', '')
            combined_prompt = oracle_prompt
        else:
            # Regular agent: allow all changes
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
        
        # Preserve Oracle-specific properties
        if is_oracle and 'oracle-agent' in agents:
            existing_oracle = agents['oracle-agent']
            agents[agent_id] = {
                'name': name,
                'provider': provider,
                'model': model,
                'prompt': combined_prompt,
                'created_at': existing_oracle.get('created_at', datetime.now().isoformat()),
                'updated_at': datetime.now().isoformat(),
                'is_oracle': True
            }
        else:
            agents[agent_id] = {
                'name': name,
                'provider': provider,
                'model': model,
                'prompt': combined_prompt,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            if is_oracle:
                agents[agent_id]['is_oracle'] = True
        
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
        # Check if this is the Oracle agent
        if agent.get('is_oracle'):
            return handle_oracle_message(agent, user_message, api_keys)
        
        # Regular agent processing
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

def handle_oracle_message(agent, user_message, api_keys):
    """Handle Oracle agent messages with access to external tools and other agents"""
    try:
        # Initialize external tools and agent communicator
        tool_manager = ExternalToolManager()
        agent_communicator = AgentCommunicator()
        
        # Get available tools and agents
        available_tools = tool_manager.get_available_tools()
        all_agents = agent_communicator.get_all_agents()
        
        # Remove Oracle from the list of agents to avoid self-communication
        other_agents = {k: v for k, v in all_agents.items() if not v.get('is_oracle')}
        
        # Build context for Oracle
        context_info = {
            'available_tools': available_tools,
            'other_agents': {agent_id: {'name': agent_info['name'], 'model': agent_info['model']} 
                           for agent_id, agent_info in other_agents.items()},
            'user_message': user_message
        }
        
        # Configure Gemini for Oracle
        gemini_client = genai.Client(api_key=api_keys['gemini'])
        chat = gemini_client.chats.create(model=agent['model'])
        
        # Send Oracle prompt with context
        enhanced_prompt = f"{agent['prompt']}\n\nCurrent Context:\n"
        enhanced_prompt += f"Available Tools: {json.dumps(available_tools, indent=2)}\n"
        enhanced_prompt += f"Other Agents: {json.dumps(context_info['other_agents'], indent=2)}\n"
        enhanced_prompt += f"User Request: {user_message}\n\n"
        enhanced_prompt += "You can use tools by responding with TOOL_CALL format: "
        enhanced_prompt += "TOOL_CALL: tool_name|param1=value1|param2=value2\n"
        enhanced_prompt += "Available tools: searchapi_search, linkedin_post, whatsapp_send_message, instagram_post, facebook_post, communicate_agent\n"
        enhanced_prompt += "For communicate_agent, use: communicate_agent|agent_id=AGENT_ID|message=YOUR_MESSAGE\n"
        
        chat.send_message(enhanced_prompt)
        
        # Get Oracle's response
        response = chat.send_message(f"Please help with: {user_message}")
        response_text = response.text
        
        # Check if Oracle wants to use tools
        if 'TOOL_CALL:' in response_text:
            return handle_oracle_tool_calls(response_text, tool_manager, agent_communicator, api_keys, chat, user_message)
        
        # Format response with summary even when no tools are used
        interaction_summary = "## 🔍 Oracle Interaction Summary\n\n"
        interaction_summary += "**Tool/Agent Interactions:** None (direct response)\n\n"
        interaction_summary += "---\n\n"
        interaction_summary += "**Oracle Response:**\n\n" + response_text
        
        return jsonify({
            'response': interaction_summary,
            'timestamp': datetime.now().isoformat(),
            'agent_type': 'oracle',
            'tools_used': [],
            'interaction_log': ['Direct response - no external tools used']
        })
        
    except Exception as e:
        return jsonify({'error': f'Oracle processing failed: {str(e)}'}), 500

def handle_oracle_tool_calls(response_text, tool_manager, agent_communicator, api_keys, chat, original_message):
    """Handle tool calls from Oracle agent"""
    try:
        # Parse all tool calls from response first
        tool_calls = []
        remaining_text = response_text
        
        while 'TOOL_CALL:' in remaining_text:
            start_idx = remaining_text.find('TOOL_CALL:')
            end_idx = remaining_text.find('\n', start_idx)
            if end_idx == -1:
                end_idx = len(remaining_text)
            
            tool_call = remaining_text[start_idx:end_idx].replace('TOOL_CALL:', '').strip()
            remaining_text = remaining_text[end_idx+1:] if end_idx < len(remaining_text) else ''
            
            # Parse tool call
            parts = tool_call.split('|')
            tool_name = parts[0].strip()
            params = {}
            
            for part in parts[1:]:
                if '=' in part:
                    key, value = part.split('=', 1)
                    params[key.strip()] = value.strip()
            
            tool_calls.append({
                'name': tool_name,
                'params': params,
                'topic': params.get('query', params.get('message', params.get('content', 'Unknown topic')))
            })
        
        if not tool_calls:
            # No tool calls found, return original response
            interaction_summary = "## 🔍 Oracle Interaction Summary\n\n"
            interaction_summary += "**Tool/Agent Interactions:** None (direct response)\n\n"
            interaction_summary += "---\n\n"
            interaction_summary += "**Oracle Response:**\n\n" + response_text
            
            return jsonify({
                'response': interaction_summary,
                'timestamp': datetime.now().isoformat(),
                'agent_type': 'oracle',
                'tools_used': [],
                'interaction_log': ['Direct response - no external tools used']
            })
        
        # Execute all tool calls and collect results
        interaction_log = []
        tool_results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            params = tool_call['params']
            interaction_topic = tool_call['topic']
            
            # Log the interaction attempt
            interaction_log.append(f"🔧 Tool: {tool_name} | Topic: {interaction_topic} | Status: Executing...")
            
            # Execute tool call
            result = execute_tool_call(tool_name, params, tool_manager, agent_communicator, api_keys)
            tool_results.append({
                'name': tool_name,
                'result': result,
                'topic': interaction_topic
            })
            
            # Update interaction log with result status
            if result.get('success'):
                interaction_log[-1] = f"✅ Tool: {tool_name} | Topic: {interaction_topic} | Status: Success"
            elif 'error' in result:
                interaction_log[-1] = f"❌ Tool: {tool_name} | Topic: {interaction_topic} | Status: Failed - {result['error']}"
            else:
                interaction_log[-1] = f"⚠️ Tool: {tool_name} | Topic: {interaction_topic} | Status: Partial - {str(result)[:100]}..."
        
        # Wait for all tool/agent responses to complete before providing final answer
        # Format comprehensive tool results for Oracle
        tool_summary = "\n\n=== COMPLETE TOOL/AGENT RESULTS ===\n\n"
        for i, tool_result in enumerate(tool_results, 1):
            tool_summary += f"--- Tool/Agent {i}: {tool_result['name']} ---\n"
            tool_summary += f"Topic: {tool_result['topic']}\n"
            tool_summary += f"Result: {json.dumps(tool_result['result'], indent=2)}\n\n"
        
        tool_summary += "=== END RESULTS ===\n\n"
        
        # Send complete results back to Oracle for final comprehensive response
        final_prompt = f"Based on ALL the tool/agent results above, provide a comprehensive final response to the user's original request: {original_message}\n\n{tool_summary}"
        final_response = chat.send_message(final_prompt)
        
        # Format interaction summary
        interaction_summary = "## 🔍 Oracle Interaction Summary\n\n"
        interaction_summary += "**Original Request:** " + original_message + "\n\n"
        interaction_summary += "**Tool/Agent Interactions:**\n"
        for log_entry in interaction_log:
            interaction_summary += f"- {log_entry}\n"
        interaction_summary += f"\n**Total Interactions:** {len(interaction_log)}\n\n"
        interaction_summary += "---\n\n"
        interaction_summary += "**Oracle Response:**\n\n" + final_response.text
        
        return jsonify({
            'response': interaction_summary,
            'timestamp': datetime.now().isoformat(),
            'agent_type': 'oracle',
            'tools_used': [tool_result['name'] for tool_result in tool_results],
            'interaction_log': interaction_log
        })
        
    except Exception as e:
        return jsonify({'error': f'Oracle tool execution failed: {str(e)}'}), 500

def execute_tool_call(tool_name, params, tool_manager, agent_communicator, api_keys):
    """Execute a specific tool call"""
    try:
        if tool_name == 'google_search':
            query = params.get('query', '')
            num_results = int(params.get('num_results', 10))
            return tool_manager.google_search(query, num_results)
        
        elif tool_name == 'linkedin_post':
            content = params.get('content', '')
            visibility = params.get('visibility', 'PUBLIC')
            return tool_manager.linkedin_post(content, visibility)
        
        elif tool_name == 'whatsapp_send_message':
            phone_number = params.get('phone_number', '')
            message = params.get('message', '')
            return tool_manager.whatsapp_send_message(phone_number, message)
        
        elif tool_name == 'instagram_post':
            image_url = params.get('image_url', '')
            caption = params.get('caption', '')
            return tool_manager.instagram_post(image_url, caption)
        
        elif tool_name == 'facebook_post':
            message = params.get('message', '')
            link = params.get('link', None)
            return tool_manager.facebook_post(message, link)
        
        elif tool_name == 'communicate_agent':
            agent_id = params.get('agent_id', '')
            message = params.get('message', '')
            return agent_communicator.communicate_with_agent(agent_id, message, api_keys)
        
        else:
            return {'error': f'Unknown tool: {tool_name}'}
            
    except Exception as e:
        return {'error': f'Tool execution failed: {str(e)}'}

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
    # Only run in debug mode when not in production
    if os.environ.get('FLASK_ENV') == 'production':
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
    else:
        app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
