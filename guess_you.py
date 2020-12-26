#!/usr/bin/python
"""
This is a echo bot.
It echoes any incoming text messages.
"""

import collections
import getopt
import emoji
import logging
import os
import random
import sys

from aiogram import Bot, Dispatcher, executor, types
from telegram.utils import helpers

# NOTE: Put here the bot's token you got from the BothFather
API_TOKEN='YOUR_BOT_TOKEN_HERE'

# Configure logging
LOG_FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

COMMANDS = [
    ('aiuto', 'Mostra istruzioni'),
    ('parole', 'Parole caricate'),
    ('riavvia', 'Inizia un nuovo gioco'),
    ('giocatori', 'Elenco dei giocatori'),
    ('partecipa', 'Aggiungiti come partecipante'),
    ('gioco1', 'Inizia una nuova partita del gioco1'),
    ('gioco2', 'Inizia una nuova partita del gioco2'),
]

ERROR_COMMAND_FROM_CHAT = '''
*Errore:* comando disponibile solo da una chat di gruppo\!'
'''

WELCOME = '''
*Benvenuti su __IndovinaTi__\!* :thumbs_up:

_Il gioco social del CoNatale 2020_\.

Per giocare: crea un nuovo gruppo con questo bot e tutti gli amici con cui vuoi giocare\.

Clicca poi su /aiuto per vedere come si gioca\.
'''

HELP = '''
Ci sono un sacco di /parole pronte per essere indovinate\.

Sono disponibili diverse modalita' di gioco:
\- /gioco1: indovina la parola che ti verra' assegnata facendo domande agli altri giocatori\.
\- /gioco2: indovina le parole assegnate agli altri giocatori facendo loro delle domande\.

In ogni modalita', ogni partecipante vedra' solo le parole che non deve indovinare ma che gli serviranno per rispondere alle domande degli altri partecipanti\.

Per indovinare una parola invece, ogni partecipante puo fare solo domande a cui si possa rispondere con un SI o NO\.

Per poter giocare servono almeno 2 /giocatori\.

Se anche tu vuoi giocare, basta cliccare su /partecipa\.

Successivamente, clicca su @IndovinaTiBot e poi \(se e' la prima volta che usi questo bot\) abilita il bot cliccando sul bottone `AVVIA` che compare in fondo alla chat\.

Sulla chat con @IndovinaTiBot riceverai le istruzioni all'inizio di ogni nuova partita, che ogni partecipante puo' avviare selezionando una delle modalita' di gioco sopra riportate\.
'''

WORDS = '''
Parole caricate per ciascuna categoria:
```
{words}
```
'''

COMMAND_NOT_FOUND = '''
*ERROR: Comando non valido\!*

Clicca /aiuto per un elenco dei comandi supportati\.
'''

NOTES_GAME1 = '''
*\.:: {chat}* \(Partita Nr\.{game}\)

Gioco: *Indovina chi sei*

Ad ogni partecipante e' assegnata una parola che dovra' indoviare facendo delle domande alle quali e' possibile rispondere solo con SI o NO\.

Anche tu hai una parola assegnata, ma ovviamnete non la sai\.\.\. altrimenti non sarebbe divertente no\? :\)

Ecco le parole assegnate agli altri partecipanti a questa partita:

```
 \- {lines}
```
'''

NOTES_GAME2 = '''
*\.:: {chat}* \(Partita Nr\.{game}\)

Gioco: *Parola nascosta*

Ogni partecipante a turno puo farti una domanda per cercare di indovinare la parola nascosta che solo tu sai\.

La parola nascosta che ti e' stata assegnata e':

```
 \- {lines}
```
'''

NOTES = [
    NOTES_GAME1, NOTES_GAME2,
]

GAME = '''
Tutti i partecipanti sono stati notificati: per vedere quali parole sono state assegnate vai al tuo @IndovinaTiBot\.

*iniziamo con le domande\!*
'''

Partecipant = collections.namedtuple('Partecipant', [
    'uid', 'username', 'name',
])

CategoryStats = collections.namedtuple('CategoryStats', [
    'category', 'count', 'used',
])

Assignement = collections.namedtuple('Assignement', [
    'player', 'category', 'word',
])

Session = collections.namedtuple('Session', [
    'id', 'name', 'state',
])


# Game status tracking
class State(object):

    def __init__(self, chat_id, chat_name):
        self._session = Session(chat_id, chat_name, state=self)
        self._words = {}
        self.reset()
        self.load()

    @property
    def session(self):
        return self._session

    def _load(self, category, data_dir='./data'):
        filepath=os.path.join(data_dir, category)
        logging.debug('Loading [%s] words for the [%s] category',
                      category, filepath)
        with open(filepath, 'r') as fh:
            category = category.replace('_e_', '_&_').replace('_', ' ').title()
            self._words[category] = fh.read().splitlines()
        self._words[category] = list(map(lambda w: w.title(),
                                     list(set(self._words[category]))))
        logging.debug('Loaded %d uniuque words for the [%s] category',
                      len(self._words[category]), category)

    def load(self):
        categories = []
        for _, _, filenames in os.walk('./data'):
            categories.extend(filenames)
        logging.debug('Categories found: %s', categories)
        logging.info('Loading categories...')
        for category in categories:
            self._load(category)
        logging.info('Categories loaded:\n%s', self.categories_report)

    def reset(self):
        self._players = []
        self._used_words = {}
        self._assignements = {}
        self._game_number = 0


    ### Players
    def add_player(self, uid, username, name):
        p = Partecipant(uid, username, name.title())
        self._players.append(Partecipant(uid, username, name))
        self._players.sort(key=lambda p: p.name)
        return p

    @property
    def players(self):
        return self._players

    @property
    def players_count(self):
        return len(self._players)

    @property
    def player_names(self):
        return [p.name for p in self.players]

    @property
    def players_report(self):
        if len(self.players) == 0:
            return 'Ancora nessuno \U0001F615'
        if len(self.players) == 1:
            msg = 'Soltanto %s \(serve almeno un\'altro concorrente\)' % (
                self.players[0].name)
            return msg
        names = ', '.join([p.name for p in self.players[:-1]])
        # Let's get the grammar right by using 'ed' for names staring with a Vocal
        last_name = self.players[-1].name
        conj = 'ed' if last_name[0] in ['A', 'E', 'I', 'O', 'U'] else 'e'
        names += ' %s %s' % (conj, last_name)
        return names


    ### Categories
    @property
    def categories(self):
        return sorted(self._words.keys())

    @property
    def categories_count(self):
        return len(self.categories)

    @property
    def categories_stats(self):
        return {c: CategoryStats(c,
                                 len(self._words[c]),
                                 len(self._used_words.get(c, [])))
                for c in self.categories}

    @property
    def categories_weight(self):
        return [self.words_left_count(c)
                for c in self.categories]

    @property
    def categories_report(self):
        cspace = max([len(c) for c in self._words])
        wspace = max([len(str(len(w))) for _,w in self._words.items()])
        uspace = max([0]+[len(str(len(w)))
                          for _,w in self._used_words.items()])
        def line(cs):
            return '%-*s : %*d (%*d / %*d)' % (
                cspace, cs.category,
                wspace, cs.count,
                uspace, cs.used,
                wspace, (cs.count - cs.used))
        lines = [line(cs)
                 for _,cs in self.categories_stats.items()]
        return '\n'.join(lines)


    ### Words
    def words(self, category='cose'):
        return self._words[category]

    def words_used(self, category='cose'):
        return self._used_words.get(category, [])

    def words_used_count(self, category='cose'):
        return len(self.words_used(category))

    def words_left_count(self, category='cose'):
        all_count = len(self.words(category))
        used_count = len(self.words_used(category))
        return all_count - used_count

    def available_words(self, category='cose'):
        allw = self.words(category)
        used = self.words_used(category)
        return list(set(allw) - set(used))

    def random_words(self, categories=None):
        categories = categories or self.categories
        available_words = [(c, w)
                           for c in self.categories
                           for w in self.available_words(c)]
        logging.debug('Available words left: %d', len(available_words))
        selected = random.sample(available_words, self.players_count)
        for c, w in selected:
            if c not in self._used_words:
                self._used_words[c] = [w]
            else:
                self._used_words[c].append(w)
        return selected


    ### Game
    @property
    def game_possible(self):
        return len(self.players) > 1

    @property
    def game_number(self):
        return self._game_number

    def game_new_round(self, game_type):
        self._game_type = game_type
        self._game_number += 1
        self._assignements = {
            p.name: Assignement(p.name, c, w)
            for p,(c,w) in zip(self.players, self.random_words())
        }
        logging.info('Assignements: %s' % self._assignements)
        logging.info('Categories stats:\n%s', self.categories_report)

    @property
    def game_notes(self):
        return NOTES[self._game_type-1]

    def game_notes_for(self, chat, name, only_others=True):
        if only_others:
            players = self.player_names
            players.remove(name)
        else:
            players = [name]
        nspace = max([len(p) for p in players])
        def line(a):
            return '%-*s : %s (%s)' % (
                nspace, a.player, a.word, a.category)
        lines = [line(self._assignements[player])
                 for player in players]
        chat = helpers.escape_markdown(chat, 2)
        msg = self.game_notes.format(chat=chat, game=self._game_number,
                                     lines='\n \- '.join(lines))
        return emoji.emojize(msg)


class Games(object):

    def __init__(self):
        self._sessions = {}

    def getState(self, message):
        if message.chat['type'] != 'group':
            return None
        chat_id = message.chat['id']
        if chat_id not in self._sessions:
            state = State(chat_id, message.chat['title'])
            self._sessions[state.session.id] = state.session
        return self._sessions[chat_id].state

# Globals
assert(API_TOKEN != 'YOUR_BOT_TOKEN_HERE')
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
games = Games()

# Telegram Handlers
@dp.message_handler(commands=['start', 'via'])
async def handle_start(message: types.Message):
    logging.info('START:\n%s', message)
    cmds = [types.BotCommand(cmd, desc) for cmd,desc in COMMANDS]
    for cmd in cmds:
        logging.debug(cmd)
    result = await bot.set_my_commands(
        [types.BotCommand(cmd, desc) for cmd,desc in COMMANDS])
    logging.info('Bot commands set: %s', result)
    await message.answer(emoji.emojize(WELCOME), parse_mode='MarkdownV2')

@dp.message_handler(commands=['restart', 'riavvia'])
async def handle_reset(message: types.Message):
    logging.info('RESTART:\n%s', message)
    state = games.getState(message)
    if not state:
        await message.answer(ERROR_COMMAND_FROM_CHAT,
                             parse_mode='MarkdownV2')

        return
    state.reset()
    logging.info('Players: %s', gy.players)
    msg = 'Nuovo gioco: *iscrizioni aperte\!*'
    await message.answer(msg, parse_mode='MarkdownV2')

@dp.message_handler(commands=['help', 'aiuto'])
async def handle_help(message: types.Message):
    logging.info('HELP:\n%s', message)
    await message.answer(emoji.emojize(HELP), parse_mode='MarkdownV2')

@dp.message_handler(commands=['words', 'parole'])
async def handle_words(message: types.Message):
    logging.info('WORDS:\n%s', message)
    state = games.getState(message)
    if not state:
        await message.answer(ERROR_COMMAND_FROM_CHAT,
                             parse_mode='MarkdownV2')
        return
    await message.answer(WORDS.format(words=state.categories_report),
                         parse_mode='MarkdownV2')

@dp.message_handler(commands=['players', 'giocatori'])
async def handle_players(message: types.Message):
    logging.info('PLAYERS:\n%s', message)
    state = games.getState(message)
    if not state:
        await message.answer(ERROR_COMMAND_FROM_CHAT,
                             parse_mode='MarkdownV2')
        return
    await message.answer('Partecipanti:\n   %s' % state.players_report,
                         parse_mode='MarkdownV2')

@dp.message_handler(commands=['enrol', 'partecipa'])
async def handle_enrol(message: types.Message):
    logging.info('ENROL:\n%s', message)
    state = games.getState(message)
    if not state:
        await message.answer(ERROR_COMMAND_FROM_CHAT,
                             parse_mode='MarkdownV2')
        return
    p = state.add_player(uid=message['from']['id'],
               username='@%s' % message['from']['username'],
               name=message['from']['first_name'])
    msg = 'Ottimo *%s* vuole giocare con noi\!' % p.name
    await message.answer(msg, parse_mode='MarkdownV2')

@dp.message_handler(commands=['play1', 'gioco1'])
async def handle_play1(message: types.Message):
    logging.info('PLAY1:\n%s', message)
    state = games.getState(message)
    if not state:
        await message.answer(ERROR_COMMAND_FROM_CHAT,
                             parse_mode='MarkdownV2')
        return
    if not state.game_possible:
        msg = 'Servono almeno due partecipanti per poter giocare'
        await message.answer(msg, parse_mode='MarkdownV2')
        return
    state.game_new_round(1)
    chat = state.session.name
    for p in state.players:
        chat_id = p.uid
        text=state.game_notes_for(chat, p.name, only_others=True)
        await bot.send_message(chat_id=chat_id, text=text,
                               parse_mode='MarkdownV2')
    await message.answer(GAME, parse_mode='MarkdownV2')

@dp.message_handler(commands=['play2', 'gioco2'])
async def handle_play2(message: types.Message):
    logging.info('PLAY2:\n%s', message)
    state = games.getState(message)
    if not state:
        await message.answer(ERROR_COMMAND_FROM_CHAT,
                             parse_mode='MarkdownV2')
        return
    if not state.game_possible:
        msg = 'Servono almeno due partecipanti per poter giocare'
        await message.answer(msg, parse_mode='MarkdownV2')
        return
    state.game_new_round(2)
    chat = state.session.name
    for p in state.players:
        chat_id = p.uid
        text=state.game_notes_for(chat, p.name, only_others=False)
        await bot.send_message(chat_id=chat_id, text=text,
                               parse_mode='MarkdownV2')
    await message.answer(GAME, parse_mode='MarkdownV2')

@dp.message_handler()
async def default(message: types.Message):
    logging.info('Default handler')
    await message.answer(COMMAND_NOT_FOUND,
                         parse_mode='MarkdownV2')


### Main
def usage(argv, errno):
    print('\n\nUsage: %s -c <category>[,<category>,...]'
          % argv[0])
    print('  <categories>: list of categories to load, default \'all\'')
    print('')
    sys.exit(errno)

def test():
    state = State(123, 'Test')
    print('TESTING')
    state.reset()
    state.load()
    print('Categories: ', state.categories)
    state.add_player(23681763, 'Derkling', 'Patrick')
    state.add_player(22266956, 'deli81', 'Elisabetta')
    state.add_player(36713985, 'crbmtt', 'Mat')
    state.add_player(17292638, '', 'Ilaria')
    print('Players: ', state.players_report)
    state.game_new_round(1)
    print(state.game_notes_for('Test', 'Patrick'))
    print(state.game_notes_for('Test', 'Elisabetta'))
    print(state.game_notes_for('Test', 'Patrick', only_others=False))
    print(state.game_notes_for('Test', 'Elisabetta', only_others=False))

    # Test multiple assignements
    print('\n\n\nRESET\n\n\n')
    state.reset()
    print(state.categories_report)
    state.add_player(23681763, 'Derkling', 'Patrick')
    state.add_player(22266956, 'deli81', 'Elisabetta')
    print('Players: ', state.players_report)
    print(state.random_words())
    print(state.categories_report)
    for i in range(10):
        state.game_new_round(1)
    print(state.categories_report)
    state.add_player(36713985, 'crbmtt', 'Mat')
    state.add_player(17292638, '', 'Ilaria')
    for i in range(10):
        state.game_new_round(1)
    print(state.categories_report)
    print(state.game_notes_for('Test', 'Patrick'))
    print(state.game_notes_for('Test', 'Elisabetta'))
    print(state.game_notes_for('Test', 'Patrick', only_others=False))
    print(state.game_notes_for('Test', 'Elisabetta', only_others=False))
    return 0

def main(argv):
    try:
        opts, args = getopt.getopt(argv[1:], "hc:t", ["categories=", "test"])
    except getopt.GetoptError:
        usage(argv, 2)

    for opt, arg in opts:
        if opt == '-h':
            usage(argv, 0)
            continue
        if opt == '-t':
            logging.getLogger().setLevel(logging.DEBUG)
            result = test()
            sys.exit(result)
    executor.start_polling(dp, skip_updates=True)

if __name__ == '__main__':
    main(sys.argv)
