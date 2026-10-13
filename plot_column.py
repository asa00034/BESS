import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
import matplotlib.pyplot as plt

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/postgres"))


column_name = 'v_a'
node_id = [13, 25, 151, 60, 101, 86, 96, 114, 450, 85]

output_dir = "node_plots"
os.makedirs(output_dir, exist_ok=True)

image_files = []

for node in node_id:
    query = (
        "SELECT ts AS time, value "
        "FROM telemetry "
        f"WHERE node_id = {node} AND signal = '{column_name}' "
        "ORDER BY ts"
    )
    df = pd.read_sql(query, engine)

    plt.figure(figsize=(10, 4))
    plt.plot(df['time'], df['value'], linewidth=0.5)
    plt.title(f"node_id: {node} | {column_name}")
    plt.xlabel('time')
    plt.ylabel(column_name)
    plt.tight_layout()

    image_path = os.path.join(output_dir, f"node_{node}.png")
    plt.savefig(image_path, dpi=150)
    plt.close()

    image_files.append((node, image_path))

html_path = os.path.join(output_dir, "node_plots.html")

with open(html_path, "w", encoding="utf-8") as f:
    f.write("<!DOCTYPE html>\n")
    f.write("<html lang=\"en\">\n<head>\n")
    f.write("<meta charset=\"UTF-8\">\n")
    f.write("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n")
    f.write("<title>Node Plots</title>\n")
    f.write("<style>\n")
    f.write("body { font-family: Arial, sans-serif; margin: 20px; }\n")
    f.write(".plot { margin-bottom: 32px; }\n")
    f.write("img { max-width: 100%; height: auto; border: 1px solid #ddd; }\n")
    f.write("h2 { margin: 0 0 8px 0; }\n")
    f.write("</style>\n</head>\n<body>\n")
    f.write(f"<h1>telemetry: {column_name}</h1>\n")

    for node, image_path in image_files:
        rel_path = os.path.relpath(image_path, output_dir).replace("\\", "/")
        f.write("<div class=\"plot\">\n")
        f.write(f"<h2>node_id: {node}</h2>\n")
        f.write(f"<img src=\"{rel_path}\" alt=\"node_id {node}\">\n")
        f.write("</div>\n")

    f.write("</body>\n</html>\n")

print(f"Saved plots to: {os.path.abspath(output_dir)}")
print(f"Open this file in your browser: {os.path.abspath(html_path)}")
