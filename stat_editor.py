# Flask editor to change the player stats automatically rather than manually

from flask import Flask, render_template, request, jsonify
import re

app = Flask(__name__)

# Regex pattern to extract player data
STAT_PATTERN = re.compile(r"(\w+): deaths=(\d+), advancements=(\d+), playtime=(\d+)")

# Store all changes
diff_store = {}

def parse_input(data):
    players = []
    for match in STAT_PATTERN.finditer(data):
        players.append({
            'name': match.group(1),
            'deaths': int(match.group(2)),
            'advancements': int(match.group(3)),
            'playtime': int(match.group(4))
        })
    return players

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        raw_data = request.form['player_data']
        players = parse_input(raw_data)
        return render_template('editor.html', players=players)
    return render_template('index.html')

@app.route('/update', methods=['POST'])
def update():
    global diff_store

    original = parse_input(request.form['original_data'])[0]
    updated = {
        'name': request.form['name'],
        'deaths': int(request.form['deaths']),
        'advancements': int(request.form['advancements']),
        'playtime': int(request.form['playtime'])
    }

    name = updated['name']

    # Update and track changes
    if name not in diff_store:
        diff_store[name] = {}

    for key in ['deaths', 'advancements', 'playtime']:
        if original[key] != updated[key]:
            diff_store[name][key] = updated[key]
        elif key in diff_store[name]:
            del diff_store[name][key]

    # Generate the output
    changes = [f"{name}: "+', '.join(f"{k}={v}" for k, v in stats.items()) for name, stats in diff_store.items() if stats]

    return jsonify({'output': '```\n' + '\n'.join(changes) + '\n```'})

if __name__ == '__main__':
    app.run(debug=True)