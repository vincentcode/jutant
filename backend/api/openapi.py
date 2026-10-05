"""Prints the API's OpenAPI document, for generating the web client's types without a server.

python -m api.openapi > ../web/openapi.json
"""

import json

from api.main import create_app

if __name__ == "__main__":
    print(json.dumps(create_app().openapi(), indent=1))
