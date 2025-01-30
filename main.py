import matplotlib
matplotlib.use('Agg')  # Usar un backend sin GUI para gráficos

import matplotlib.pyplot as plt
from flask import Flask, request, jsonify, render_template
from flask.cli import load_dotenv
import requests
import os
from datetime import datetime, timedelta
from collections import defaultdict
import io
import base64
from scipy.interpolate import make_interp_spline
import numpy as np

app = Flask(__name__)
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

# Cargar variables de entorno desde .env
load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO")

# Aquí continuaría el resto de tu código


def get_week_start(date):
    return (date - timedelta(days=date.weekday())).date()

def fetch_contributors_lines():
    if not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
        raise ValueError("Las variables de entorno GITHUB_TOKEN, GITHUB_OWNER y GITHUB_REPO deben estar definidas.")
    
    contributors = defaultdict(lambda: {'additions': 0, 'deletions': 0})
    has_next_page = True
    end_cursor = None

    while has_next_page:
        query = f"""
        {{
          repository(owner: "{GITHUB_OWNER}", name: "{GITHUB_REPO}") {{
            defaultBranchRef {{
              target {{
                ... on Commit {{
                  history(first: 100, after: {f'\"{end_cursor}\"' if end_cursor else 'null'}) {{
                    edges {{
                      node {{
                        author {{
                          user {{
                            login
                          }}
                        }}
                        committedDate
                        additions
                        deletions
                      }}
                    }}
                    pageInfo {{
                      hasNextPage
                      endCursor
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
        """
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
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
            additions = edge.get('node', {}).get('additions', 0)
            deletions = edge.get('node', {}).get('deletions', 0)
            if author and committed_date_str:
                username = author.get('login')
                if username:
                    # Acumula las líneas añadidas y eliminadas por contribuidor
                    contributors[username]['additions'] += additions
                    contributors[username]['deletions'] += deletions

        page_info = history.get('pageInfo', {})
        has_next_page = page_info.get('hasNextPage', False)
        end_cursor = page_info.get('endCursor', None)

    return contributors


def fetch_contributors():
    if not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
        raise ValueError("Las variables de entorno GITHUB_TOKEN, GITHUB_OWNER y GITHUB_REPO deben estar definidas.")
    
    contributors = defaultdict(lambda: defaultdict(int))
    has_next_page = True
    end_cursor = None

    while has_next_page:
        query = f"""
        {{
          repository(owner: "{GITHUB_OWNER}", name: "{GITHUB_REPO}") {{
            defaultBranchRef {{
              target {{
                ... on Commit {{
                  history(first: 100, after: {f'\"{end_cursor}\"' if end_cursor else 'null'}) {{
                    edges {{
                      node {{
                        author {{
                          user {{
                            login
                          }}
                        }}
                        committedDate
                      }}
                    }}
                    pageInfo {{
                      hasNextPage
                      endCursor
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
        """
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
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
@app.route('/contributors_lines', methods=['GET'])
def contributors_lines():
    try:
        contributors = fetch_contributors_lines()
        if not contributors:
            return jsonify({"error": "No se encontraron contribuyentes"}), 404
        
        usernames = list(contributors.keys())
        additions = [contributors[username]['additions'] for username in usernames]
        deletions = [contributors[username]['deletions'] for username in usernames]

        # Ordenar contribuyentes por la cantidad total de líneas modificadas (añadidas + eliminadas)
        sorted_contributors = sorted(zip(usernames, additions, deletions), key=lambda x: x[1] + x[2], reverse=True)
        usernames, additions, deletions = zip(*sorted_contributors)

        # Gráfico Apilado para Líneas Añadidas y Eliminadas
        fig, ax = plt.subplots(figsize=(10, 6))

        ax.bar(usernames, additions, label='Líneas Añadidas', color='green', alpha=0.7)
        ax.bar(usernames, deletions, bottom=additions, label='Líneas Eliminadas', color='red', alpha=0.7)

        ax.set_xlabel('Usuarios')
        ax.set_ylabel('Líneas')
        ax.set_title('Líneas Añadidas y Eliminadas por Usuario')
        ax.legend()

        # Agregar etiquetas con los valores de líneas añadidas y eliminadas
        for i, (add, delete) in enumerate(zip(additions, deletions)):
            ax.text(i, add / 2, "+"+str(add), ha='center', color='black', fontsize=10, fontweight='bold')
            ax.text(i, add + delete / 2 + 450, "-"+str(delete), ha='center', color='black', fontsize=10, fontweight='bold')

        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        # Guardar el gráfico en formato PNG y convertirlo a base64
        img_io = io.BytesIO()
        plt.savefig(img_io, format='png')
        img_io.seek(0)
        img_b64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
        plt.close()

        return render_template('lines.html', img_data=img_b64)
    
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Ocurrió un error inesperado", "message": str(e)}), 500


@app.route('/contributors_graph', methods=['GET'])
def contributors_graph():
    try:
        contributors = fetch_contributors()
        if not contributors:
            return jsonify({"error": "No se encontraron contribuyentes"}), 404
        
        weeks = sorted(set(contributors.keys()))
        usernames = sorted({user for week_data in contributors.values() for user in week_data})
        
        img_data_list = []
        for username in usernames:
            user_commits = [contributors[week].get(username, 0) for week in weeks]
            
            x = np.array(range(len(weeks)))
            y = np.array(user_commits)
            spline = make_interp_spline(x, y, k=3)
            x_new = np.linspace(x.min(), x.max(), 500)
            y_new = spline(x_new)

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(x_new, y_new, label=username, color='b')
            ax.scatter(x, y, color='r', zorder=5)
            ax.set_xticks(x)
            ax.set_xticklabels([str(week) for week in weeks], rotation=45)
            ax.set_xlabel('Semana')
            ax.set_ylabel('Número de Commits')
            ax.set_title(f'Contribuciones Semanales de {username}')
            ax.legend()
            ax.set_ylim(0, 60)
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
@app.route('/')
def index():
    try:
        contributors = fetch_contributors()
        if not contributors:
            return jsonify({"error": "No se encontraron contribuyentes"}), 404
        
        # Aggregate commits by user (summed over all weeks)
        user_commits = defaultdict(int)
        for week_data in contributors.values():
            for username, commit_count in week_data.items():
                user_commits[username] += commit_count
        
        # Prepare data for graphs
        usernames = list(user_commits.keys())
        commits = list(user_commits.values())

        # Gráfico de Barras
        fig, ax = plt.subplots()
        ax.bar(usernames, commits, color='skyblue')
        ax.set_xlabel('Usuarios')
        ax.set_ylabel('Commits')
        ax.set_title('Commits por Usuario')
        plt.xticks(rotation=45)
        plt.tight_layout()
        img_io = io.BytesIO()
        plt.savefig(img_io, format='png')
        img_io.seek(0)
        bar_chart = base64.b64encode(img_io.getvalue()).decode('utf-8')
        plt.close()

        # Gráfico Circular
        fig, ax = plt.subplots()
        ax.pie(commits, labels=usernames, autopct='%1.1f%%', colors=plt.cm.Paired.colors, startangle=140)
        ax.set_title('Distribución de Commits')
        plt.tight_layout()
        img_io = io.BytesIO()
        plt.savefig(img_io, format='png')
        img_io.seek(0)
        pie_chart = base64.b64encode(img_io.getvalue()).decode('utf-8')
        plt.close()

        # Pass images to template
        return render_template('index.html', bar_chart=bar_chart, pie_chart=pie_chart)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Ocurrió un error inesperado", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
