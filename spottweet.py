from twython import Twython, TwythonError

class SpotTweet:
    
    def __init__(self, consumer, consumer_sec, access, access_sec):
        try:
            self.api = Twython(consumer, consumer_sec, access, access_sec)
        except Exception as e:
            self.api = None
            raise Exception(f"Twython {e.error_code}")

    def tweet(self, mesg):
        return self.tweet_as_reply(mesg, None)
    
    def tweet_as_reply(self, mesg, repl_id = None):
        if not repl_id:
            try:
                res = self.api.update_status(status=mesg)
            except TwythonError as e:
                raise Exception(f"Twython {e.error_code}:{mesg}")
        else:
            try:
                res = self.api.update_status(status=mesg, in_reply_to_status_id=repl_id, auto_populate_reply_metadata=True)
            except TwythonError as e:
                raise Exception(f"Twython {e.error_code}:{mesg}")

        if res:
            return res['id']
        else:
            return None

    def get_direct_messages(self):
        try:
            return self.api.get_direct_messages()
        except TwythonError as e:
            raise Exception(f"Twython DM {e.error_code}")

    def send_direct_message(self, mesg):
        try:
            self.api.send_direct_message(event = mesg)
        except TwythonError as e:
            raise Exception(f"Twython DM {e.error_code}")

