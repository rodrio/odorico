import os
import requests
import json
from typing import Dict, Any, Optional

class ExternalToolManager:
    """Manages external API tools for the Oracle agent"""
    
    def __init__(self):
        self.api_keys = {
            'searchapi': os.environ.get('SEARCHAPI_API_KEY'),
            'linkedin': os.environ.get('LINKEDIN_API_KEY'),
            'meta': os.environ.get('META_API_KEY')
        }
    
    def get_available_tools(self) -> Dict[str, bool]:
        """Returns a dictionary of available tools and their status"""
        return {
            'searchapi': bool(self.api_keys['searchapi']),
            'linkedin': bool(self.api_keys['linkedin']),
            'whatsapp': bool(self.api_keys['meta']),
            'instagram': bool(self.api_keys['meta']),
            'facebook': bool(self.api_keys['meta'])
        }
    
    def searchapi_search(self, query: str, num_results: int = 10) -> Dict[str, Any]:
        """Perform search using SearchAPI.io"""
        if not self.get_available_tools()['searchapi']:
            return {'error': 'SearchAPI.io API key not configured'}
        
        try:
            url = 'https://www.searchapi.io/api/v1/search'
            params = {
                'engine': 'google',
                'q': query,
                'api_key': self.api_keys['searchapi'],
                'num': min(num_results, 10)
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            # Extract organic results from SearchAPI.io response
            for item in data.get('organic_results', []):
                results.append({
                    'title': item.get('title', ''),
                    'link': item.get('link', ''),
                    'snippet': item.get('snippet', ''),
                    'displayLink': item.get('link', '').split('/')[2] if '/' in item.get('link', '') else ''
                })
            
            return {
                'success': True,
                'query': query,
                'total_results': data.get('search_information', {}).get('total_results', str(len(results))),
                'results': results
            }
            
        except Exception as e:
            return {'error': f'SearchAPI.io search failed: {str(e)}'}
    
    def linkedin_post(self, content: str, visibility: str = 'PUBLIC') -> Dict[str, Any]:
        """Post to LinkedIn"""
        if not self.get_available_tools()['linkedin']:
            return {'error': 'LinkedIn API key not configured'}
        
        try:
            # LinkedIn API v2 share endpoint
            url = 'https://api.linkedin.com/v2/shares'
            headers = {
                'Authorization': f'Bearer {self.api_keys["linkedin"]}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'content': {
                    'contentEntities': [],
                    'title': content[:100]  # LinkedIn has character limits
                },
                'distribution': {
                    'linkedInDistributionTarget': {
                        'visibleToGuest': visibility == 'PUBLIC'
                    }
                },
                'owner': 'urn:li:person:CURRENT_USER',  # This needs to be replaced with actual person URN
                'subject': content[:100],
                'text': {
                    'text': content
                }
            }
            
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            return {
                'success': True,
                'post_id': response.json().get('id'),
                'message': 'LinkedIn post created successfully'
            }
            
        except Exception as e:
            return {'error': f'LinkedIn post failed: {str(e)}'}
    
    def whatsapp_send_message(self, phone_number: str, message: str) -> Dict[str, Any]:
        """Send WhatsApp message via Meta API"""
        if not self.get_available_tools()['whatsapp']:
            return {'error': 'Meta API key not configured for WhatsApp'}
        
        try:
            # Meta WhatsApp Cloud API
            url = f'https://graph.facebook.com/v18.0/PHONE_NUMBER_ID/messages'
            headers = {
                'Authorization': f'Bearer {self.api_keys["meta"]}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'messaging_product': 'whatsapp',
                'to': phone_number,
                'type': 'text',
                'text': {
                    'body': message
                }
            }
            
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            return {
                'success': True,
                'message_id': response.json().get('messages', [{}])[0].get('id'),
                'message': 'WhatsApp message sent successfully'
            }
            
        except Exception as e:
            return {'error': f'WhatsApp message failed: {str(e)}'}
    
    def instagram_post(self, image_url: str, caption: str) -> Dict[str, Any]:
        """Post to Instagram"""
        if not self.get_available_tools()['instagram']:
            return {'error': 'Meta API key not configured for Instagram'}
        
        try:
            # First create media container
            container_url = 'https://graph.facebook.com/v18.0/INSTAGRAM_BUSINESS_ACCOUNT_ID/media'
            headers = {
                'Authorization': f'Bearer {self.api_keys["meta"]}',
                'Content-Type': 'application/json'
            }
            
            container_payload = {
                'image_url': image_url,
                'caption': caption
            }
            
            container_response = requests.post(container_url, headers=headers, json=container_payload)
            container_response.raise_for_status()
            container_id = container_response.json().get('id')
            
            # Then publish the media
            publish_url = f'https://graph.facebook.com/v18.0/INSTAGRAM_BUSINESS_ACCOUNT_ID/media_publish'
            publish_payload = {
                'creation_id': container_id
            }
            
            publish_response = requests.post(publish_url, headers=headers, json=publish_payload)
            publish_response.raise_for_status()
            
            return {
                'success': True,
                'media_id': publish_response.json().get('id'),
                'message': 'Instagram post created successfully'
            }
            
        except Exception as e:
            return {'error': f'Instagram post failed: {str(e)}'}
    
    def facebook_post(self, message: str, link: Optional[str] = None) -> Dict[str, Any]:
        """Post to Facebook"""
        if not self.get_available_tools()['facebook']:
            return {'error': 'Meta API key not configured for Facebook'}
        
        try:
            url = 'https://graph.facebook.com/v18.0/PAGE_ID/feed'
            headers = {
                'Authorization': f'Bearer {self.api_keys["meta"]}',
                'Content-Type': 'application/json'
            }
            
            payload = {'message': message}
            if link:
                payload['link'] = link
            
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            return {
                'success': True,
                'post_id': response.json().get('id'),
                'message': 'Facebook post created successfully'
            }
            
        except Exception as e:
            return {'error': f'Facebook post failed: {str(e)}'}

class AgentCommunicator:
    """Manages communication between agents"""
    
    def __init__(self, agents_file: str = 'config/agents.json'):
        self.agents_file = agents_file
    
    def get_all_agents(self) -> Dict[str, Any]:
        """Get all available agents"""
        try:
            with open(self.agents_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific agent"""
        agents = self.get_all_agents()
        return agents.get(agent_id)
    
    def communicate_with_agent(self, agent_id: str, message: str, api_keys: Dict[str, str]) -> Dict[str, Any]:
        """Send a message to another agent and get response"""
        agent = self.get_agent_info(agent_id)
        if not agent:
            return {'error': f'Agent {agent_id} not found'}
        
        try:
            # Import here to avoid circular imports
            import google.genai as genai
            from openai import OpenAI
            import anthropic
            
            provider = agent.get('provider', 'gemini')
            api_key = api_keys.get(provider, '')
            
            if not api_key:
                return {'error': f'{provider.title()} API key not configured for agent communication'}
            
            if provider == 'gemini':
                client = genai.Client(api_key=api_key)
                chat = client.chats.create(model=agent['model'])
                
                if agent['prompt']:
                    chat.send_message(agent['prompt'])
                
                response = chat.send_message(message)
                return {
                    'success': True,
                    'agent_name': agent['name'],
                    'response': response.text
                }
                
            elif provider == 'openai':
                client = OpenAI(api_key=api_key)
                
                messages = []
                if agent['prompt']:
                    messages.append({'role': 'system', 'content': agent['prompt']})
                messages.append({'role': 'user', 'content': message})
                
                response = client.chat.completions.create(
                    model=agent['model'],
                    messages=messages,
                    max_tokens=2000
                )
                
                return {
                    'success': True,
                    'agent_name': agent['name'],
                    'response': response.choices[0].message.content
                }
                
            elif provider == 'anthropic':
                client = anthropic.Anthropic(api_key=api_key)
                
                messages = []
                if agent['prompt']:
                    messages.append({'role': 'user', 'content': agent['prompt']})
                    messages.append({'role': 'assistant', 'content': 'I understand. I will act according to these instructions.'})
                messages.append({'role': 'user', 'content': message})
                
                response = client.messages.create(
                    model=agent['model'],
                    max_tokens=2000,
                    messages=messages
                )
                
                return {
                    'success': True,
                    'agent_name': agent['name'],
                    'response': response.content[0].text
                }
            
            else:
                return {'error': f'Unknown provider: {provider}'}
                
        except Exception as e:
            return {'error': f'Agent communication failed: {str(e)}'}

def execute_tool_call(tool_name, params, tool_manager, agent_communicator, api_keys):
    """Execute a specific tool call"""
    try:
        if tool_name == 'searchapi_search':
            query = params.get('query', '')
            num_results = int(params.get('num_results', 10))
            return tool_manager.searchapi_search(query, num_results)
        
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
