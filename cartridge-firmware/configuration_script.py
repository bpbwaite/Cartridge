Import("env")

if env.IsIntegrationDump():
   Return()


import os
import shutil

precompile_script_success: bool = False
def pre(*_):
    # runs pre compilation but post project configuration
    print('Custom pre compilation script running now')
    if os.path.exists('./include/temp_batch_game_list.h'):
        print('Warning: header file injection is broken, games list will not be copied')
        return
    if os.path.exists('./include/batch_game_list_local.h'):
        shutil.move('./include/batch_game_list.h', './include/temp_batch_game_list.h')
        shutil.copy2('./include/batch_game_list_local.h', './include/batch_game_list.h')
    global precompile_script_success
    precompile_script_success = True

def post(source, target, env):
    # runs after the .hex firmware has been generated
    if not precompile_script_success:
        print('Skipping post-compilation script')
        return
    print('Custom post-compilation script running now')
    if os.path.exists('./include/temp_batch_game_list.h'):
        shutil.move('./include/temp_batch_game_list.h', './include/batch_game_list.h')

pre()

env.AddPostAction("$BUILD_DIR/${PROGNAME}.hex", post)