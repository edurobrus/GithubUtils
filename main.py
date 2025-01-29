from flask import Flask, request, jsonify, render_template
import requests
from datetime import datetime, timedelta
from collections import defaultdict
import matplotlib.pyplot as plt
import io
import base64
from scipy.interpolate import make_interp_spline
import numpy as np

app = Flask(__name__)
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

def get_week_start(date):
    return (date - timedelta(days=date.weekday())).date()

def fetch_contributors(owner, repo, token):
    contributors = defaultdict(lambda: defaultdict(int))
    has_next_page = True
    end_cursor = None

    while has_next_page:
        query = """
        {
          repository(owner: "%s", name: "%s") {
            defaultBranchRef {
              target {
                ... on Commit {
                  history(first: 100, after: %s) {
                    edges {
                      node {
                        author {
                          user {
                            login
                          }
                        }
                        committedDate
                      }
                    }
                    pageInfo {
                      hasNextPage
                      endCursor
                    }
                  }
                }
              }
            }
          }
        }
        """ % (owner, repo, f'"{end_cursor}"' if end_cursor else "null")

        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(GITHUB_GRAPHQL_URL, json={'query': query}, headers=headers)
        data = response.json()
        
        if 'data' not in data or data['data'] is None:
            raise ValueError("Error en la respuesta de la API de GitHub.")
        
        history = data.get('data', {}).get('repository', {}).get('defaultBranchRef', {}).get('target', {}).get('history', {})
        if not history or 'edges' not in history:
            raise ValueError("No se encontraron contribuciones.")
        
        for edge in history['edges']:
            author = edge.get('node', {}).get('author', {}).get('user', {})
            committed_date_str = edge.get('node', {}).get('committedDate', '')
            if author and committed_date_str:
                username = author.get('login')
                if username:
                    committed_date = datetime.strptime(committed_date_str, "%Y-%m-%dT%H:%M:%SZ")
                    week_start = get_week_start(committed_date)
                    contributors[week_start][username] += 1

        page_info = history.get('pageInfo', {})
        has_next_page = page_info.get('hasNextPage', False)
        end_cursor = page_info.get('endCursor', None)

    return contributors

@app.route('/contributors_graph', methods=['GET'])
def contributors_graph():
    owner = request.args.get('owner')
    repo = request.args.get('repo')
    token = request.args.get('token')
    
    if not owner or not repo or not token:
        return jsonify({"error": "Se requieren owner, repo y token"}), 400
    
    try:
        contributors = fetch_contributors(owner, repo, token)
        if not contributors:
            return jsonify({"error": "No se encontraron contribuyentes"}), 404
        
        weeks = sorted(set(contributors.keys()))
        usernames = sorted({user for week_data in contributors.values() for user in week_data})
        
        img_data_list = []
        for username in usernames:
            user_commits = [contributors[week].get(username, 0) for week in weeks]
            
            # Create smooth spline curve using `make_interp_spline`
            x = np.array(range(len(weeks)))
            y = np.array(user_commits)
            spline = make_interp_spline(x, y, k=3)  # cubic spline interpolation
            x_new = np.linspace(x.min(), x.max(), 500)  # Smooth curve
            y_new = spline(x_new)

            # Plotting the graph
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(x_new, y_new, label=username, color='b')
            ax.scatter(x, y, color='r', zorder=5)  # Original data points
            ax.set_xticks(x)  # Set x-ticks to original weeks
            ax.set_xticklabels([str(week) for week in weeks], rotation=45)
            ax.set_xlabel('Semana')
            ax.set_ylabel('Número de Commits')
            ax.set_title(f'Contribuciones Semanales de {username}')
            ax.legend()
            ax.set_ylim(0, 60)  # Establece el límite del eje Y de 0 a 60
            plt.tight_layout()

            img_io = io.BytesIO()
            plt.savefig(img_io, format='png')
            img_io.seek(0)
            img_b64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
            plt.close()
            
            img_data_list.append({'username': username, 'img_data': img_b64})
        
        return render_template('graph.html', img_data_list=img_data_list)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Ocurrió un error inesperado", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
