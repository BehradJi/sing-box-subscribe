import json, os, tool, time, requests, sys, importlib, argparse, yaml, ruamel.yaml
import re
from datetime import datetime
from urllib.parse import urlparse
from collections import OrderedDict
# Handle optional import for Vercel compatibility
try:
    from api.app import TEMP_DIR
except:
    TEMP_DIR = None
from parsers.clash2base64 import clash2v2ray
from gh_proxy_helper import set_gh_proxy

parsers_mod = {}
providers = None
color_code = [31, 32, 33, 34, 35, 36, 91, 92, 93, 94, 95, 96]

def loop_color(text):
    text = '\033[1;{color}m{text}\033[0m'.format(color=color_code[0], text=text)
    color_code.append(color_code.pop(0))
    return text

def init_parsers():
    b = os.walk('parsers')
    for path, dirs, files in b:
        for file in files:
            f = os.path.splitext(file)
            if f[1] == '.py':
                parsers_mod[f[0]] = importlib.import_module('parsers.' + f[0])

def get_template():
    template_dir = 'config_template'
    if not os.path.exists(template_dir): return []
    template_files = os.listdir(template_dir)
    template_list = [os.path.splitext(file)[0] for file in template_files if file.endswith('.json')]
    template_list.sort()
    return template_list

def load_json(path):
    return json.loads(tool.readFile(path))

def process_subscribes(subscribes):
    nodes = {}
    # Safely check for ech parameter
    ech_enabled = providers.get('ech') == '1' or providers.get('ech') == 1
    
    for subscribe in subscribes:
        if 'enabled' in subscribe and not subscribe['enabled']:
            continue
        _nodes = get_nodes(subscribe['url'])
        if _nodes:
            # Inject ECH settings only if requested to save time
            if ech_enabled:
                for node in _nodes:
                    if node.get('type') == 'vless' and 'tls' in node:
                        if node['tls'].get('enabled', False):
                            node['tls']['ech'] = {"enabled": True}
            
            add_prefix(_nodes, subscribe)
            add_emoji(_nodes, subscribe)
            nodefilter(_nodes, subscribe)
            
            tag = subscribe['tag']
            if subscribe.get('subgroup'):
                tag = tag + '-' + subscribe['subgroup'] + '-' + 'subgroup'
            
            if not nodes.get(tag):
                nodes[tag] = []
            nodes[tag] += _nodes
    
    tool.proDuplicateNodeName(nodes)
    return nodes

# ... (Include all other helper functions: nodes_filter, get_nodes, parse_content, etc., same as before)

def save_config(path, nodes):
    # Completely bypass disk writing on Vercel to avoid Read-only filesystem error
    if os.environ.get('VERCEL'):
        return
    try:
        tool.saveFile(path, json.dumps(nodes, indent=2, ensure_ascii=False))
    except:
        pass

if __name__ == '__main__':
    init_parsers()
    parser = argparse.ArgumentParser()
    parser.add_argument('--temp_json_data', type=str, help='Temporary JSON Data')
    parser.add_argument('--template_index', type=int, help='Template Index')
    args = parser.parse_args()
    
    # 1. Robust JSON parsing to prevent 'str' has no attribute 'get'
    providers = None
    if args.temp_json_data:
        try:
            providers = json.loads(args.temp_json_data)
            if isinstance(providers, str):
                providers = json.loads(providers)
        except:
            providers = args.temp_json_data

    if not isinstance(providers, dict):
        providers = load_json('providers.json')

    # 2. Load the appropriate config template
    if providers.get('config_template'):
        try:
            response = requests.get(providers['config_template'], timeout=5)
            config = response.json()
        except:
            config = load_json('config_template/default.json') # Fallback
    else:
        template_list = get_template()
        uip = select_config_template(template_list, selected_template_index=args.template_index)
        config = load_json(f'config_template/{template_list[uip]}.json')

    # 3. Process subscription and ECH injection
    nodes = process_subscribes(providers.get("subscribes", []))

    # 4. Assemble final configuration
    if providers.get('Only-nodes'):
        final_config = [node for contents in nodes.values() for node in contents]
    else:
        final_config = combin_to_config(config, nodes)

    # 5. Output result (Print is required for the API to receive the data)
    print(json.dumps(final_config))
    
    # Attempt to save only if NOT on Vercel
    save_path = providers.get("save_config_path", "config.json")
    save_config(save_path, final_config)
