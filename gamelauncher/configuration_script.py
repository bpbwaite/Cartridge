Import("env")

import os
import shutil


def pre():
    # runs pre compilation but post project configuration
    print('Custom p-e compilation running')
    if os.path.exists('include/batch_game_list_local.h'):
        shutil.move('include/batch_game_list.h', 'include/temp_batch_game_list.h')
        shutil.move('include/batch_game_list_local.h', 'include/batch_game_list.h')

def post(source, target, env):
    print('Custom post-copmilation running')
    if os.path.exists('include/temp_batch_game_list.h'):
        shutil.move('include/batch_game_list.h', 'include/batch_game_list_local.h')
        shutil.move('include/temp_batch_game_list.h', 'include/batch_game_list.h')

pre()

env.AddPostAction("$BUILD_DIR/${PROGNAME}.hex", post)


    



