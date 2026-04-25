"""
Luke Family Cookbook — Flask Backend
====================================
Secured API with shared family password for write operations.

Setup:
  1. Edit config.json and set your family password
  2. Run: python app.py
  3. Share the password with family members
"""

import json
import os
import re
import shutil
from datetime import datetime
from flask import Flask, request, jsonify, send_file, send_from_directory

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'Cookbook.json')
FAVORITES_FILE = os.path.join(BASE_DIR, 'favorites.json')
CHANGELOG_FILE = os.path.join(BASE_DIR, 'changelog.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')
IMAGES_DIR = os.path.join(BASE_DIR, 'images')


# ─── Security ──────────────────────────────────────────────

def load_config():
    """Load config, creating default if it doesn't exist."""
    if not os.path.exists(CONFIG_FILE):
        default = {'write_password': 'changeme'}
        save_json(CONFIG_FILE, default)
        print(f"\n⚠️  Created {CONFIG_FILE} with default password 'changeme'.")
        print(f"   Edit this file and set your family's password before sharing the site.\n")
    return load_json(CONFIG_FILE, {})


def check_write_auth(data):
    """Verify the write password. Returns error response or None if OK."""
    config = load_config()
    password = config.get('write_password', '')
    if not password or password == 'changeme':
        # No password set — allow writes (dev mode)
        return None
    submitted = (data or {}).get('_password', '')
    if submitted != password:
        return jsonify({'error': 'Incorrect password', 'auth_required': True}), 403
    return None


def sanitize_string(s):
    """Strip HTML tags and null bytes from a string."""
    if not isinstance(s, str):
        return s
    # Remove HTML tags
    s = re.sub(r'<[^>]+>', '', s)
    # Remove null bytes
    s = s.replace('\x00', '')
    return s.strip()


def sanitize_recipe_data(data):
    """Sanitize all string fields in recipe data."""
    text_fields = ['Category', 'Subcategory', 'Recipe Name', 'Notes',
                   'Source', 'Ingredients', 'Instructions']
    for field in text_fields:
        if field in data and isinstance(data[field], str):
            data[field] = sanitize_string(data[field])
    # Sanitize related recipe names
    if 'Related Recipes' in data and isinstance(data['Related Recipes'], list):
        data['Related Recipes'] = [sanitize_string(r) for r in data['Related Recipes'] if isinstance(r, str)]
    # Sanitize extra locations
    if 'Extra Locations' in data and isinstance(data['Extra Locations'], list):
        for loc in data['Extra Locations']:
            if isinstance(loc, dict):
                for k in ['Category', 'Subcategory']:
                    if k in loc and isinstance(loc[k], str):
                        loc[k] = sanitize_string(loc[k])
    return data


@app.after_request
def add_security_headers(response):
    """Add security headers to every response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
    )
    return response


# ─── File helpers ───────────────────────────────────────────

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_recipes():
    return load_json(DATA_FILE, [])

def save_recipes(recipes):
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    if os.path.exists(DATA_FILE):
        shutil.copy2(DATA_FILE, os.path.join(BACKUP_DIR, f'Cookbook_{ts}.json'))
    backups = sorted(os.listdir(BACKUP_DIR))
    while len(backups) > 50:
        os.remove(os.path.join(BACKUP_DIR, backups.pop(0)))
    save_json(DATA_FILE, recipes)

def load_favorites():
    return load_json(FAVORITES_FILE, {})

def load_changelog():
    return load_json(CHANGELOG_FILE, [])


# ─── Recipe helpers ─────────────────────────────────────────

def validate_recipe(data):
    if not data.get('Recipe Name', '').strip():
        return 'Recipe Name is required'
    if not data.get('Category', '').strip():
        return 'Category is required'
    if not data.get('Subcategory', '').strip():
        return 'Subcategory is required'
    return None

def build_recipe(data):
    return {
        'Category':        data.get('Category', '').strip(),
        'Subcategory':     data.get('Subcategory', '').strip(),
        'Recipe Name':     data.get('Recipe Name', '').strip(),
        'Notes':           data.get('Notes', '').strip(),
        'Source':          data.get('Source', '').strip(),
        'Ingredients':     data.get('Ingredients', '').strip(),
        'Instructions':    data.get('Instructions', '').strip(),
        'Related Recipes': data.get('Related Recipes', []),
        'Extra Locations': data.get('Extra Locations', []),
    }

def recipe_matches_key(recipe, key):
    name = recipe.get('Recipe Name', '')
    if key == name:
        return True
    source = recipe.get('Source', '')
    if source and key == f"{name} — {source}":
        return True
    return False

def sync_related(recipes, recipe_name, old_related, new_related):
    added = set(new_related) - set(old_related)
    removed = set(old_related) - set(new_related)
    for r in recipes:
        rel = r.get('Related Recipes', [])
        for key in added:
            if recipe_matches_key(r, key) and recipe_name not in rel:
                rel.append(recipe_name)
                r['Related Recipes'] = rel
        for key in removed:
            if recipe_matches_key(r, key) and recipe_name in rel:
                rel.remove(recipe_name)
                r['Related Recipes'] = rel

def get_changed_fields(old, new):
    fields = ['Recipe Name', 'Source', 'Notes', 'Category', 'Subcategory',
              'Ingredients', 'Instructions', 'Related Recipes', 'Extra Locations']
    return [f for f in fields if old.get(f, '') != new.get(f, '')]

def log_change(user, action, recipe_name, before=None, changed_fields=None):
    log = load_changelog()
    entry = {
        'timestamp': datetime.now().isoformat(),
        'user': user or 'Someone',
        'action': action,
        'recipe_name': recipe_name,
    }
    if before is not None:
        entry['before'] = before
    if changed_fields:
        entry['changed_fields'] = changed_fields
    log.insert(0, entry)
    save_json(CHANGELOG_FILE, log[:200])


# ─── Routes: pages and static ──────────────────────────────

@app.route('/')
def index():
    return send_file(os.path.join(BASE_DIR, 'index.html'))

@app.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(IMAGES_DIR, filename)


# ─── Routes: auth check ────────────────────────────────────

@app.route('/api/auth-check', methods=['POST'])
def auth_check():
    """Verify a password without making any changes."""
    data = request.get_json() or {}
    auth_err = check_write_auth(data)
    if auth_err:
        return auth_err
    return jsonify({'ok': True})


# ─── Routes: recipes ───────────────────────────────────────

@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    return jsonify(load_recipes())

@app.route('/api/recipes', methods=['POST'])
def add_recipe():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    auth_err = check_write_auth(data)
    if auth_err:
        return auth_err
    data = sanitize_recipe_data(data)
    error = validate_recipe(data)
    if error:
        return jsonify({'error': error}), 400

    recipe = build_recipe(data)
    recipes = load_recipes()
    recipes.append(recipe)
    sync_related(recipes, recipe['Recipe Name'], [], recipe.get('Related Recipes', []))
    save_recipes(recipes)

    log_change(sanitize_string(data.get('_user', '')), 'added', recipe['Recipe Name'])
    return jsonify({'index': len(recipes) - 1, 'recipe': recipe}), 201

@app.route('/api/recipes/<int:idx>', methods=['PUT'])
def update_recipe(idx):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    auth_err = check_write_auth(data)
    if auth_err:
        return auth_err
    data = sanitize_recipe_data(data)
    error = validate_recipe(data)
    if error:
        return jsonify({'error': error}), 400

    recipes = load_recipes()
    if idx < 0 or idx >= len(recipes):
        return jsonify({'error': 'Recipe not found'}), 404

    old_recipe = recipes[idx]
    old_name = old_recipe.get('Recipe Name', '')
    old_related = old_recipe.get('Related Recipes', [])

    new_recipe = build_recipe(data)
    new_name = new_recipe['Recipe Name']
    new_related = new_recipe.get('Related Recipes', [])

    recipes[idx] = new_recipe

    if old_name != new_name:
        for r in recipes:
            rel = r.get('Related Recipes', [])
            if old_name in rel:
                rel[rel.index(old_name)] = new_name
        favs = load_favorites()
        changed = False
        for u, fl in favs.items():
            if old_name in fl:
                fl[fl.index(old_name)] = new_name
                changed = True
        if changed:
            save_json(FAVORITES_FILE, favs)

    sync_related(recipes, new_name, old_related, new_related)
    save_recipes(recipes)

    changed = get_changed_fields(old_recipe, new_recipe)
    log_change(sanitize_string(data.get('_user', '')), 'edited', new_name, before=old_recipe, changed_fields=changed)
    return jsonify({'index': idx, 'recipe': recipes[idx]})

@app.route('/api/recipes/<int:idx>', methods=['DELETE'])
def delete_recipe(idx):
    data = request.get_json() or {}
    auth_err = check_write_auth(data)
    if auth_err:
        return auth_err

    recipes = load_recipes()
    if idx < 0 or idx >= len(recipes):
        return jsonify({'error': 'Recipe not found'}), 404

    deleted = recipes.pop(idx)
    deleted_name = deleted.get('Recipe Name', '')
    deleted_source = deleted.get('Source', '')
    deleted_key = f"{deleted_name} — {deleted_source}" if deleted_source else deleted_name

    for r in recipes:
        rel = r.get('Related Recipes', [])
        if deleted_name in rel:
            rel.remove(deleted_name)
        if deleted_key in rel:
            rel.remove(deleted_key)

    save_recipes(recipes)

    favs = load_favorites()
    favorited_by = [user for user, fav_list in favs.items() if deleted_name in fav_list]
    changed = False
    for user, fav_list in favs.items():
        if deleted_name in fav_list:
            fav_list.remove(deleted_name)
            changed = True
    if changed:
        favs = {u: fl for u, fl in favs.items() if fl}
        save_json(FAVORITES_FILE, favs)

    deleted['_favorited_by'] = favorited_by
    log_change(sanitize_string(data.get('_user', '')), 'deleted', deleted_name, before=deleted)
    return jsonify({'deleted': deleted_name})


# ─── Routes: restore ───────────────────────────────────────

@app.route('/api/restore', methods=['POST'])
def restore_recipe():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    auth_err = check_write_auth(data)
    if auth_err:
        return auth_err

    ci = data.get('changelog_index')
    user = sanitize_string(data.get('_user', 'Someone'))
    log = load_changelog()

    if ci is None or ci < 0 or ci >= len(log):
        return jsonify({'error': 'Invalid changelog entry'}), 400

    entry = log[ci]
    action = entry.get('action', '')
    recipe_name = entry.get('recipe_name', '')
    is_restored = entry.get('restored', False)

    recipes = load_recipes()

    if not is_restored:
        # ── UNDO ──
        if action == 'added':
            found = -1
            for i, r in enumerate(recipes):
                if r.get('Recipe Name', '') == recipe_name:
                    found = i
                    break
            if found < 0:
                return jsonify({'error': 'Recipe not found'}), 404
            snapshot = recipes.pop(found)
            for r in recipes:
                rel = r.get('Related Recipes', [])
                if recipe_name in rel:
                    rel.remove(recipe_name)
            save_recipes(recipes)
            log[ci]['redo_snapshot'] = snapshot
            log[ci]['restored'] = True
            save_json(CHANGELOG_FILE, log)
            return jsonify({'toggled': 'undone'})

        before = entry.get('before')
        if not before:
            return jsonify({'error': 'No snapshot to restore'}), 400

        if action == 'deleted' or action.startswith('undid'):
            recipe = build_recipe(before)
            recipes.append(recipe)
            name = recipe.get('Recipe Name', '')
            sync_related(recipes, name, [], recipe.get('Related Recipes', []))
            save_recipes(recipes)
            favorited_by = before.get('_favorited_by', [])
            if favorited_by:
                favs = load_favorites()
                for fu in favorited_by:
                    uf = favs.get(fu, [])
                    if name not in uf:
                        uf.append(name)
                        favs[fu] = uf
                save_json(FAVORITES_FILE, favs)
            log[ci]['restored'] = True
            save_json(CHANGELOG_FILE, log)
            return jsonify({'toggled': 'undone'})

        elif action == 'edited':
            found = -1
            for i, r in enumerate(recipes):
                if r.get('Recipe Name', '') == recipe_name:
                    found = i
                    break
            if found < 0:
                return jsonify({'error': 'Recipe not found'}), 404
            current = recipes[found]
            recipe = build_recipe(before)
            recipes[found] = recipe
            name = recipe.get('Recipe Name', '')
            sync_related(recipes, name, current.get('Related Recipes', []), recipe.get('Related Recipes', []))
            save_recipes(recipes)
            log[ci]['redo_snapshot'] = current
            log[ci]['restored'] = True
            save_json(CHANGELOG_FILE, log)
            return jsonify({'toggled': 'undone'})

    else:
        # ── REDO ──
        if action == 'added':
            snapshot = entry.get('redo_snapshot')
            if not snapshot:
                return jsonify({'error': 'No snapshot to redo'}), 400
            recipe = build_recipe(snapshot)
            recipes.append(recipe)
            name = recipe.get('Recipe Name', '')
            sync_related(recipes, name, [], recipe.get('Related Recipes', []))
            save_recipes(recipes)
            log[ci]['restored'] = False
            save_json(CHANGELOG_FILE, log)
            return jsonify({'toggled': 'redone'})

        elif action == 'deleted' or action.startswith('undid'):
            found = -1
            for i, r in enumerate(recipes):
                if r.get('Recipe Name', '') == recipe_name:
                    found = i
                    break
            if found < 0:
                return jsonify({'error': 'Recipe not found'}), 404
            recipes.pop(found)
            for r in recipes:
                rel = r.get('Related Recipes', [])
                if recipe_name in rel:
                    rel.remove(recipe_name)
            save_recipes(recipes)
            log[ci]['restored'] = False
            save_json(CHANGELOG_FILE, log)
            return jsonify({'toggled': 'redone'})

        elif action == 'edited':
            snapshot = entry.get('redo_snapshot')
            if not snapshot:
                return jsonify({'error': 'No snapshot to redo'}), 400
            found = -1
            for i, r in enumerate(recipes):
                if r.get('Recipe Name', '') == recipe_name or r.get('Recipe Name', '') == (entry.get('before', {}).get('Recipe Name', '')):
                    found = i
                    break
            if found < 0:
                return jsonify({'error': 'Recipe not found'}), 404
            recipe = build_recipe(snapshot)
            current = recipes[found]
            recipes[found] = recipe
            name = recipe.get('Recipe Name', '')
            sync_related(recipes, name, current.get('Related Recipes', []), recipe.get('Related Recipes', []))
            save_recipes(recipes)
            log[ci]['restored'] = False
            save_json(CHANGELOG_FILE, log)
            return jsonify({'toggled': 'redone'})

    return jsonify({'error': 'Nothing to do'}), 400


# ─── Routes: favorites (no password required) ──────────────

@app.route('/api/favorites', methods=['GET'])
def get_favorites():
    return jsonify(load_favorites())

@app.route('/api/favorites', methods=['POST'])
def toggle_favorite():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    user = sanitize_string((data.get('user') or '').strip())
    recipe_name = sanitize_string((data.get('recipe_name') or '').strip())
    if not user or not recipe_name:
        return jsonify({'error': 'user and recipe_name required'}), 400

    favs = load_favorites()
    user_favs = favs.get(user, [])

    if recipe_name in user_favs:
        user_favs.remove(recipe_name)
        action = 'removed'
    else:
        user_favs.append(recipe_name)
        action = 'added'

    if user_favs:
        favs[user] = user_favs
    elif user in favs:
        del favs[user]

    save_json(FAVORITES_FILE, favs)
    return jsonify({'action': action, 'user': user, 'recipe_name': recipe_name})


# ─── Routes: changelog ─────────────────────────────────────

@app.route('/api/changelog', methods=['GET'])
def get_changelog():
    return jsonify(load_changelog())


# ─── Run locally ────────────────────────────────────────────

if __name__ == '__main__':
    load_config()  # Create default config if needed
    app.run(debug=True, port=8000)
