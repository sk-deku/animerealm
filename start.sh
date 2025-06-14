echo "Cloning Repo ...."
git clone https://github.com/sk-deku/animerealm /animerealm
cd /animerealm
pip install -r requirements.txt
echo "Starting bot...."
python3 main.py
