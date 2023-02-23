How to run this project locally

1. Clone repo, cd into the directory
2. optionally create a virtual environment and activate it (keeps all dependencies in the virtual environment, without installing globally)
3. run `pip install -r requirements.txt`
4. create a spotify developer account, retrieve your client id and client secret key, store it in the following env vars
    `SPOTIFY_CLIENT_ID`
    `SPOTIFY_CLIENT_SECRET`
5. install MongoDB and run it locally
6. set the environment variable `ENV` to `dev`
7. run `python app.py` and you should now be able to interact with the api on localhost:7000
