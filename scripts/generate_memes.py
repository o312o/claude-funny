#!/usr/bin/env python3
"""
Claude Memes Auto-Generator
Generates new Claude user memes using AI (Ollama via Cloudflare Tunnel / Gemma cloud).
Searches Reddit for trending Claude memes and adds source references.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests'])
    import requests

MEMES_FILE = Path(__file__).parent.parent / 'claude-memes' / 'memes.json'
OLLAMA_ENDPOINT = os.environ.get('OLLAMA_ENDPOINT', '')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'hermes')
GEMMA_API_KEY = os.environ.get('GEMMA_API_KEY', '')
MAX_NEW_MEMES = int(os.environ.get('MAX_NEW_MEMES', '5'))


def load_memes():
    with open(MEMES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_memes(data):
    data['meta']['total'] = len(data['memes'])
    data['meta']['lastUpdated'] = datetime.utcnow().strftime('%Y-%m-%d')
    with open(MEMES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_imgflip_templates():
    """Fetch top meme templates from imgflip API."""
    try:
        r = requests.get('https://api.imgflip.com/get_memes', timeout=15)
        if r.ok:
            return r.json().get('data', {}).get('memes', [])
    except Exception as e:
        print(f'[imgflip] Error: {e}')
    return []


def search_reddit(query='claude AI meme', subreddits=None):
    """Search Reddit for Claude-related meme posts."""
    if subreddits is None:
        subreddits = ['ClaudeAI', 'ProgrammerHumor', 'ChatGPT', 'singularity']
    headers = {'User-Agent': 'ClaudeMemeBot/1.0 (github.com)'}
    found = []
    for sub in subreddits:
        try:
            r = requests.get(
                f'https://www.reddit.com/r/{sub}/search.json',
                params={'q': query, 'sort': 'new', 'limit': 10, 't': 'week'},
                headers=headers, timeout=15
            )
            if not r.ok:
                continue
            for post in r.json().get('data', {}).get('children', []):
                d = post.get('data', {})
                if d.get('post_hint') == 'image' or d.get('is_gallery'):
                    found.append({
                        'title': d.get('title', ''),
                        'url': d.get('url', ''),
                        'permalink': f'https://reddit.com{d.get("permalink", "")}',
                        'subreddit': sub,
                        'score': d.get('score', 0),
                    })
        except Exception as e:
            print(f'[reddit/{sub}] Error: {e}')
    return sorted(found, key=lambda x: x['score'], reverse=True)


def call_ollama(prompt):
    """Call Ollama API via Cloudflare Tunnel endpoint."""
    if not OLLAMA_ENDPOINT:
        return None
    try:
        r = requests.post(
            f'{OLLAMA_ENDPOINT}/api/generate',
            json={'model': OLLAMA_MODEL, 'prompt': prompt, 'stream': False, 'format': 'json'},
            timeout=120
        )
        if r.ok:
            return r.json().get('response', '')
    except Exception as e:
        print(f'[ollama] Error: {e}')
    return None


def call_gemma(prompt):
    """Call Google Gemma API."""
    if not GEMMA_API_KEY:
        return None
    try:
        r = requests.post(
            f'https://generativelanguage.googleapis.com/v1beta/models/gemma-3-27b-it:generateContent',
            params={'key': GEMMA_API_KEY},
            json={'contents': [{'parts': [{'text': prompt}]}]},
            timeout=120
        )
        if r.ok:
            return r.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        print(f'[gemma] Error: {e}')
    return None


def generate_meme_ideas(existing_titles, template_keys):
    """Generate new meme ideas using available AI backends."""
    sample_titles = existing_titles[:40]
    prompt = f"""You are a meme creator for Claude AI users (Thai audience). Generate {MAX_NEW_MEMES} NEW funny memes about Claude AI user problems.

Categories (pick one per meme):
- free: Free tier problems (rate limits, no Opus, waiting)
- pro: Paid tier problems (expensive, still has limits, API bills)
- code: Claude Code / vibe coding problems (not reading code, accepting all, bugs)
- all-users: Universal problems (sycophancy, hallucination, refusals, long responses)
- culture: AI culture (Claude vs ChatGPT, prompt engineering, AI welfare debates)

Available meme template keys: {', '.join(template_keys[:50])}

EXISTING memes (DO NOT repeat these ideas):
{chr(10).join(f'- {t}' for t in sample_titles)}

Return a JSON array. Each object:
{{
  "c": "category_key",
  "b": "Thai badge label",
  "t": "Short Thai title (mix Thai+English)",
  "d": "Thai description of the joke",
  "k": "template_key from the list above",
  "top": "Top meme text (Thai, short, Impact font style)",
  "bot": "Bottom meme text (Thai, short)",
  "mid": "Optional middle text or empty string"
}}

Make them funny, relatable, and specific to real Claude user experiences. Mix Thai and English naturally. Use current Claude features: Opus, Sonnet, Haiku, Extended Thinking, Claude Code, Artifacts, Projects, MCP, rate limits, $20 Pro, $100 Max plans."""

    result = call_ollama(prompt)
    if not result:
        result = call_gemma(prompt)
    if not result:
        print('[ai] No AI backend available, skipping generation')
        return []

    try:
        match = re.search(r'\[[\s\S]*\]', result)
        if match:
            ideas = json.loads(match.group())
            valid = []
            for idea in ideas:
                if all(k in idea for k in ('c', 'b', 't', 'd', 'k', 'top', 'bot')):
                    if idea['k'] in template_keys:
                        idea.setdefault('mid', '')
                        valid.append(idea)
            return valid[:MAX_NEW_MEMES]
    except (json.JSONDecodeError, KeyError) as e:
        print(f'[ai] Parse error: {e}')
    return []


def main():
    print(f'=== Claude Memes Generator ===')
    print(f'Time: {datetime.utcnow().isoformat()}Z')

    data = load_memes()
    existing_titles = [m['t'] for m in data['memes']]
    template_keys = list(data['templates'].keys())
    print(f'Current: {len(data["memes"])} memes, {len(template_keys)} templates')

    # 1. Refresh imgflip templates
    imgflip = fetch_imgflip_templates()
    new_templates = 0
    for tpl in imgflip:
        key = tpl['name'].lower().replace(' ', '_').replace("'", '')[:20]
        if key not in data['templates']:
            data['templates'][key] = [str(tpl['id']), tpl['url']]
            template_keys.append(key)
            new_templates += 1
    if new_templates:
        print(f'[imgflip] Added {new_templates} new templates (total: {len(data["templates"])})')

    # 2. Search Reddit for references
    reddit_refs = search_reddit()
    if reddit_refs:
        print(f'[reddit] Found {len(reddit_refs)} meme references:')
        ref_file = MEMES_FILE.parent / 'references.jsonl'
        with open(ref_file, 'a', encoding='utf-8') as f:
            for ref in reddit_refs[:10]:
                print(f'  - [{ref["subreddit"]}] {ref["title"][:60]} (score:{ref["score"]})')
                f.write(json.dumps(ref, ensure_ascii=False) + '\n')

    # 3. Generate new memes with AI
    new_ideas = generate_meme_ideas(existing_titles, template_keys)
    added = 0
    for idea in new_ideas:
        if idea['t'] in existing_titles:
            continue
        next_id = max((m.get('id', 0) for m in data['memes']), default=0) + 1
        idea['id'] = next_id
        idea['source'] = 'ai-generated'
        idea['addedDate'] = datetime.utcnow().strftime('%Y-%m-%d')
        data['memes'].append(idea)
        existing_titles.append(idea['t'])
        added += 1
        print(f'  + [{idea["c"]}] {idea["t"]}')

    if added > 0 or new_templates > 0:
        save_memes(data)
        print(f'\n✅ Added {added} memes. Total: {len(data["memes"])}')
    else:
        print('\nℹ️  No changes made.')

    # Output for GitHub Actions
    gh_output = os.environ.get('GITHUB_OUTPUT', '')
    if gh_output:
        with open(gh_output, 'a') as f:
            f.write(f'added={added}\n')
            f.write(f'total={len(data["memes"])}\n')
            f.write(f'references={len(reddit_refs)}\n')


if __name__ == '__main__':
    main()
