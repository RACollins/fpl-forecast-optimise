import numpy as np
import pandas as pd
import base64
import requests


def get_requests_response(url_template, **kwargs):
    response = requests.get(
        url_template.format(**kwargs)
            )
    response_json = response.json()
    return response_json

def jaccard_sim(df):
    columns = df.columns
    jaccard_matrix = np.empty([len(columns), len(columns)])
    for i, row in enumerate(columns):
        for j, col in enumerate(columns):
            jaccard_sim = len(set(df[row]).intersection(set(df[col]))) / len(
                set(df[row]).union(set(df[col]))
            )
            jaccard_matrix[i, j] = jaccard_sim
    jaccard_sim_df = pd.DataFrame(index=columns, columns=columns, data=jaccard_matrix)
    return jaccard_sim_df


def get_img_as_base64(file):
    with open(file, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

def human_readable(num):
    if num > 1000000:
        if not num % 1000000:
            return f"{num // 1000000}M"
        return f"{round(num / 1000000, 1)}M"
    return f"{num // 1000}K"