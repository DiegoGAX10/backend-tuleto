from flask import Flask, jsonify
from flask_cors import CORS
from sshtunnel import SSHTunnelForwarder
import mysql.connector
import warnings
import traceback
import os
from dotenv import load_dotenv

load_dotenv()

warnings.filterwarnings("ignore")

app = Flask(__name__)
CORS(app)

# =============================================
# CONEXIÓN CON SSHTUNNEL
# =============================================
def conectar():
    tunnel = SSHTunnelForwarder(
        (os.environ.get('SSH_HOST'), int(os.environ.get('SSH_PORT', 22))),
        ssh_username=os.environ.get('SSH_USER'),
        ssh_password=os.environ.get('SSH_PASSWORD'),
        remote_bind_address=('127.0.0.1', int(os.environ.get('DB_PORT', 3306)))
    )
    tunnel.start()

    conn = mysql.connector.connect(
        host=os.environ.get('DB_HOST'),
        port=tunnel.local_bind_port,
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD'),
        database=os.environ.get('DB_NAME')
    )
    return tunnel, conn

# =============================================
# ENDPOINT - HEALTH CHECK
# =============================================
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "API corriendo"})

# =============================================
# ENDPOINT - PIEZAS
# =============================================
@app.route('/api/piezas', methods=['GET'])
def get_piezas():
    tunnel = None
    try:
        tunnel, conn = conectar()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                pd.id_produccion                                        AS id_produccion,
                pd.fecha                                                AS fecha,
                pd.hora_inicio                                          AS hora_inicio,
                pd.hora_fin                                             AS hora_fin,
                pd.id_empleado                                          AS id_empleado,
                pd.id_pieza                                             AS id_pieza,
                p.tipo_pieza                                            AS tipo_pieza,
                p.tiempo_estimado_minutos                               AS tiempo_estimado,
                TIMESTAMPDIFF(MINUTE, pd.hora_inicio, pd.hora_fin)      AS tiempo_real,
                (TIMESTAMPDIFF(MINUTE, pd.hora_inicio, pd.hora_fin)
                    - p.tiempo_estimado_minutos)                        AS diferencia_tiempo,
                CASE
                    WHEN TIMESTAMPDIFF(MINUTE, pd.hora_inicio, pd.hora_fin)
                         > p.tiempo_estimado_minutos THEN 'Excedido'
                    ELSE 'En tiempo'
                END                                                     AS estado_tiempo,
                pd.cantidad_producida                                   AS cantidad_producida,
                p.costo_unitario                                        AS costo_unitario,
                (pd.cantidad_producida * p.costo_unitario)              AS costo_total,
                pd.observaciones                                        AS observaciones,
                CASE
                    WHEN pd.observaciones LIKE '%defectuoso%' THEN 1
                    ELSE 0
                END                                                     AS es_defectuosa
            FROM Producciones_Diarias pd
            JOIN Piezas p ON pd.id_pieza = p.id_pieza
            WHERE pd.id_pieza IS NOT NULL
            ORDER BY pd.fecha, pd.id_pieza
            LIMIT 1000
        """)
        rows = cursor.fetchall()

        for row in rows:
            for key, val in row.items():
                if hasattr(val, 'isoformat'):
                    row[key] = str(val)

        cursor.close()
        conn.close()
        return jsonify({"status": "ok", "total": len(rows), "data": rows})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if tunnel:
            tunnel.stop()

# =============================================
# ENDPOINT - STATS
# =============================================
@app.route('/api/stats', methods=['GET'])
def get_stats():
    tunnel = None
    try:
        tunnel, conn = conectar()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN observaciones LIKE '%defectuoso%' THEN 1 ELSE 0 END) AS defectuosas,
                SUM(CASE WHEN observaciones NOT LIKE '%defectuoso%'
                    OR observaciones IS NULL THEN 1 ELSE 0 END)                    AS normales,
                ROUND(AVG(TIMESTAMPDIFF(MINUTE, hora_inicio, hora_fin)), 2)        AS tiempo_promedio
            FROM Producciones_Diarias
            WHERE id_pieza IS NOT NULL
        """)
        stats = cursor.fetchone()
        cursor.close()
        conn.close()
        return jsonify({"status": "ok", "data": stats})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if tunnel:
            tunnel.stop()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)