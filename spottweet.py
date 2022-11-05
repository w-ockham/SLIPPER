import sys
from twython import Twython, TwythonError

class SpotTweet:
    def __init__(self, consumer, consumer_sec, access, access_sec):
        try:
            self.api = Twython(consumer, consumer_sec, access, access_sec)
        except Exception as e:
            self.api = None
            print(f"Error twython {e.error_code}", file=sys.stderr)

    def tweet(self, mesg):
        return self.tweet_as_reply(mesg, None)
    
    def tweet_as_reply(self, mesg, repl_id = None):
        if not repl_id:
            try:
                res = self.api.update_status(status=mesg)
            except TwythonError as e:
                print(f"Error Twython {e.error_code}:{mesg}", file=sys.stderr)
                res = None
        else:
            try:
                res = self.api.update_status(status=mesg, in_reply_to_status_id=repl_id, auto_populate_reply_metadata=True)
            except TwythonError as e:
                print(f"Error Twython {e.error_code}:{mesg}", file=sys.stderr)
                res = None

        if res:
            return res['id']
        else:
            return None
