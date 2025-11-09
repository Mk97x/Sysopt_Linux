import requests
import os
from dotenv import load_dotenv
from typing import Dict, Any


load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY")
IP = os.getenv("IP")



class LLMClient:
    """
    A client for interacting with the AnythingLLM API.

    This class allows sending chat messages to a workspace and retrieving responses.
    Supports optional authentication via Bearer token.
    """

    def __init__(self, api_url: str = None, api_key: str = None, workspace_slug: str = "test"):
        """
        Initialize the LLMClient.

        Args:
            api_url (str, optional): Base URL for the AnythingLLM API.
                Defaults to "http://{IP}/api/v1/workspace/{workspace_slug}/chat".
            api_key (str, optional): Bearer token for authorization.
                Defaults to value from LLM_API_KEY.
            workspace_slug (str): Workspace slug to send messages to.
                Defaults to "default".
        """
        # Use provided URL or construct from IP and workspace
        self.api_url = api_url or f"http://{IP}/api/v1/workspace/{workspace_slug}/chat"
        self.api_key = api_key or LLM_API_KEY

    def get_workspace_chats(self, workspace_slug: str = "default") -> Dict[str, Any]:
        """
        Retrieve recent chats from a workspace.

        Args:
            workspace_slug (str): Workspace slug to fetch chats from.
            limit (int): Number of recent chats to fetch.

        Returns:
            Dict[str, Any]: JSON response containing chats or error.
        """
        headers = {"accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        chats_url = f"http://{IP}/api/v1/workspace/{workspace_slug}/chats"

        print(f"Fetching chats from: {chats_url}")
        print(f"Headers: {headers}")

        response = None  # <- Definiere `response` außerhalb des try-Blocks

        try:
            response = requests.get(chats_url, headers=headers, timeout=30)
            response.raise_for_status()

            # DEBUG: Print the raw response before parsing JSON
            print("Raw response:", response.text[:500])  # Nur ersten 500 Zeichen
            print("Status Code:", response.status_code)
            print("Headers:", dict(response.headers))

            return response.json()
        except requests.exceptions.HTTPError as e:
            status_code = getattr(response, 'status_code', 'N/A')
            return {"error": f"HTTP error occurred: {e}", "status_code": status_code}
        except requests.exceptions.JSONDecodeError as e:
            return {
                "error": f"JSON decode error: {e}",
                "raw_response": response.text if response else "No response object",
                "status_code": getattr(response, 'status_code', 'N/A'),
                "headers": getattr(response, 'headers', {})
            }
        except requests.exceptions.RequestException as e:
            return {
                "error": f"Request failed: {e}",
                "raw_response": response.text if response else "No response object",
                "headers": getattr(response, 'headers', {})
            }
        except Exception as e:
            return {"error": f"Unexpected error: {e}"}

    def run_prompt(self, prompt: str, mode: str = "chat") -> Dict[str, Any]:
        """
        Send a message to the AnythingLLM workspace and retrieve the response.

        Args:
            prompt (str): The input message to send to the workspace.
            mode (str): Chat mode, either "query" or "chat". Defaults to "query".

        Returns:
            Dict[str, Any]: JSON response from the API or an error dictionary.
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {"message": prompt, "mode": mode}

        # print(f"Sending request to: {self.api_url}")  # <- DEBUG
        # print(f"Headers: {headers}")                  # <- DEBUG
        # print(f"Payload: {payload}")                  # <- DEBUG

        response = None  # <- Definiere `response` außerhalb des try-Blocks

        try:
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=300)
            response.raise_for_status()

            # DEBUG: Print the raw response before parsing JSON
            # print("Raw response:", response.text[:200])  # Nur ersten 200 Zeichen
            # print("Status Code:", response.status_code)
            # print("Headers:", dict(response.headers))

            return response.json()
        except requests.exceptions.HTTPError as e:
            status_code = getattr(response, 'status_code', 'N/A')
            return {"error": f"HTTP error occurred: {e}", "status_code": status_code}
        except requests.exceptions.JSONDecodeError as e:
            return {
                "error": f"JSON decode error: {e}",
                "raw_response": response.text if response else "No response object",
                "status_code": getattr(response, 'status_code', 'N/A'),
                "headers": getattr(response, 'headers', {})
            }
        except requests.exceptions.RequestException as e:
            return {
                "error": f"Request failed: {e}",
                "raw_response": response.text if response else "No response object",
                "headers": getattr(response, 'headers', {})
            }
        except Exception as e:
            return {"error": f"Unexpected error: {e}"}


if __name__ == "__main__":
    client = LLMClient(workspace_slug="test")
    response = client.run_prompt("say hello", mode="chat")
    print("Chat response:", response)