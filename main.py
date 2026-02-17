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
    
    # Use 'str' instead of 'parse_json' for the initial catch to prevent 
    # Python 3.14 type-checking errors during the handshake.
    parser.add_argument('--temp_json_data', type=str, help='临时内容')
    parser.add_argument('--template_index', type=int, help='模板序号')
    parser.add_argument('--gh_proxy_index', type=str, help='github加速链接')
    
    # Use parse_known_args() instead of parse_args()
    # This prevents the "unrecognized arguments" crash if Flask sends extra data
    args, unknown = parser.parse_known_args()
    
    temp_json_data = args.temp_json_data
    
    # Handle JSON parsing manually for better error control
    providers = None
    if temp_json_data and temp_json_data != '{}':
        try:
            providers = json.loads(temp_json_data)
            # Handle double-encoded strings from Vercel
            if isinstance(providers, str):
                providers = json.loads(providers)
        except Exception as e:
            print(f"JSON Parsing Error: {e}")
            providers = load_json('providers.json')
    else:
        providers = load_json('providers.json')

    # Load Template Logic
    if providers.get('config_template'):
        config_template_path = providers['config_template']
        print('选择: \033[33m' + config_template_path + '\033[0m')
        response = requests.get(providers['config_template'], timeout=10)
        response.raise_for_status()
        config = response.json()
    else:
        template_list = get_template()
        if len(template_list) < 1:
            print('没有找到模板文件')
            sys.exit()
        uip = select_config_template(template_list, selected_template_index=args.template_index)
        config_template_path = 'config_template/' + template_list[uip] + '.json'
        print('选择: \033[33m' + template_list[uip] + '.json\033[0m')
        config = load_json(config_template_path)

    # Process Nodes
    nodes = process_subscribes(providers["subscribes"])

    # GH Proxy Logic - Now safer
    if args.gh_proxy_index and str(args.gh_proxy_index).isdigit():
        gh_idx = int(args.gh_proxy_index)
        if "route" in config and "rule_set" in config["route"]:
            urls = [item["url"] for item in config["route"]["rule_set"]]
            new_urls = set_gh_proxy(urls, gh_idx)
            for item, new_url in zip(config["route"]["rule_set"], new_urls):
                item["url"] = new_url

    # Generate Final Output
    if providers.get('Only-nodes'):
        final_config = [node for contents in nodes.values() for node in contents]
    else:
        final_config = combin_to_config(config, nodes)

    # Save logic (Environment aware)
    save_path = providers.get("save_config_path", "config.json")
    if os.environ.get('VERCEL'):
        print("Vercel detected: Outputting JSON to stdout.")
    else:
        save_config(save_path, final_config)
    
    # Crucial for the API to receive the data
    print(json.dumps(final_config))
