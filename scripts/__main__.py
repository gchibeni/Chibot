import os
from getpass import getpass
from colorama import Fore
from colorama import Style

file = 'token.secret'
exists = os.path.isfile(f'./{file}')

# Checks if token exists and creates it.
if not exists:
    exists = True
    token = getpass(f'{Fore.YELLOW}> Enter BOT token: *{Style.RESET_ALL}')
    with open(file, "w+") as f:
        f.write(token)
    print(f'{Fore.YELLOW}> TOKEN CREATED{Style.RESET_ALL}')
# If it exists start up the bot.
if exists:
    import scripts.chibot
