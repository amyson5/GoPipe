#!/usr/bin/env python3

from gtpPipe import GtpPipe


def main():
    # default to 2 remote engines.
    # to add more engine:
    # add to list before start the script, or type 'append_engine n' in gtp shell during play.
    # to enable local engine:
    # change local to True, or type 'append_engine 0' in gtp shell during play
    engines = [1, 2]
    pipe = GtpPipe(engines, local=False)

    while True:
        ipt_line = input()

        try:
            command = ipt_line
            if "quit" in command:
                print(f"= \n\n")
                break
            pipe(command)
        except Exception as e:
            pipe.logger.error(f"Error in sending command {command} to pipe.\n{e}")


if __name__ == "__main__":
    main()
