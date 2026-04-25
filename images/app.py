"""
Luke Family Cookbook — Flask Backend
====================================
A tiny API that reads and writes Cookbook.json.

Routes:
  GET  /                    → Serve the app (index.html)
  GET  /api/recipes         → Return all recipes as JSON
  POST /api/recipes         → Add a new recipe
  PUT  /api/recipes/<index> → Update a recipe
  DELETE /api/recipes/<index> → Delete a recipe
"""

import json
import os
import shutil
from datetime import datetime
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# ─── Configuration ──────────────────────────────────────────
# Path to the JSON data file (same folder as this script)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'Cookbook.json')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')


# ─── Helpers ────────────────────────────────────────────────

def load_recipes():
    """Read recipes from the JSON file."""
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_recipes(recipes):
    """Write recipes to the JSON file, creating a backup first."""
    # Create a timestamped backup before overwriting
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'Cookbook_{timestamp}.json')
    shutil.copy2(DATA_FILE, backup_path)

    # Keep only the 20 most recent backups
    backups = sorted(os.listdir(BACKUP_DIR))
    while len(backups) > 20:
        os.remove(os.path.join(BACKUP_DIR, backups.pop(0)))

    # Write the updated data
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(recipes, f, indent=2, ensure_ascii=False)


def validate_recipe(data):
    """Check that a recipe has the required fields. Returns error message or None."""
    if not data.get('Recipe Name', '').strip():
        return 'Recipe Name is required'
    if not data.get('Category', '').strip():
        return 'Category is required'
    if not data.get('Subcategory', '').strip():
        return 'Subcategory is required'
    return None


# ─── Routes ─────────────────────────────────────────────────

@app.route('/')
def index():
    """Serve the main app page."""
    return send_file(os.path.join(BASE_DIR, 'index.html'))


@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    """Return all recipes."""
    recipes = load_recipes()
    return jsonify(recipes)


@app.route('/api/recipes', methods=['POST'])
def add_recipe():
    """Add a new recipe. Expects JSON body with recipe fields."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    error = validate_recipe(data)
    if error:
        return jsonify({'error': error}), 400

    # Build a clean recipe object with all expected fields
    recipe = {
        'Category':     data.get('Category', '').strip(),
        'Subcategory':  data.get('Subcategory', '').strip(),
        'Recipe Name':  data.get('Recipe Name', '').strip(),
        'Notes':        data.get('Notes', '').strip(),
        'Source':       data.get('Source', '').strip(),
        'Ingredients':  data.get('Ingredients', '').strip(),
        'Instructions': data.get('Instructions', '').strip(),
    }

    recipes = load_recipes()
    recipes.append(recipe)
    save_recipes(recipes)

    return jsonify({'index': len(recipes) - 1, 'recipe': recipe}), 201


@app.route('/api/recipes/<int:idx>', methods=['PUT'])
def update_recipe(idx):
    """Update an existing recipe by index."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    error = validate_recipe(data)
    if error:
        return jsonify({'error': error}), 400

    recipes = load_recipes()

    if idx < 0 or idx >= len(recipes):
        return jsonify({'error': 'Recipe not found'}), 404

    recipes[idx] = {
        'Category':     data.get('Category', '').strip(),
        'Subcategory':  data.get('Subcategory', '').strip(),
        'Recipe Name':  data.get('Recipe Name', '').strip(),
        'Notes':        data.get('Notes', '').strip(),
        'Source':       data.get('Source', '').strip(),
        'Ingredients':  data.get('Ingredients', '').strip(),
        'Instructions': data.get('Instructions', '').strip(),
    }

    save_recipes(recipes)

    return jsonify({'index': idx, 'recipe': recipes[idx]})


@app.route('/api/recipes/<int:idx>', methods=['DELETE'])
def delete_recipe(idx):
    """Delete a recipe by index."""
    recipes = load_recipes()

    if idx < 0 or idx >= len(recipes):
        return jsonify({'error': 'Recipe not found'}), 404

    deleted = recipes.pop(idx)
    save_recipes(recipes)

    return jsonify({'deleted': deleted['Recipe Name']})


# ─── Run locally ────────────────────────────────────────────
# This block only runs when you execute `python app.py` directly.
# On PythonAnywhere, the WSGI server imports the app — this block is skipped.

if __name__ == '__main__':
    app.run(debug=True, port=8000)
