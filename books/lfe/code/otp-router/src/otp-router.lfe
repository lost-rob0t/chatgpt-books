(defmodule otp-router
  "OTP gen_server wrapper around the Event Routing DSL semantic kernel."
  (export (start_link 1)
          (request 2)
          (route 2)
          (replace-rules 2)
          (get-rules 1)
          (crash 1)
          (stop 0))
  (export (init 1)
          (handle_call 3)
          (handle_cast 2)
          (handle_info 2)
          (terminate 2)
          (code_change 3))
  (behaviour gen_server))

(defun start_link (rules)
  (gen_server:start_link
   (tuple 'local 'otp-router)
   'otp-router
   rules
   ()))

(defun request (request timeout)
  (gen_server:call 'otp-router request timeout))

(defun route (event timeout)
  (request (tuple 'route event) timeout))

(defun replace-rules (rules timeout)
  (request (tuple 'replace-rules rules) timeout))

(defun get-rules (timeout)
  (request 'get-rules timeout))

(defun crash (reason)
  (gen_server:cast 'otp-router (tuple 'crash reason)))

(defun stop ()
  (gen_server:stop 'otp-router))

(defun init (rules)
  (tuple 'ok rules))

(defun handle_call
  ([(tuple 'route event) _from rules]
   (tuple 'reply (event-rules:route event rules) rules))
  ([(tuple 'replace-rules new-rules) _from _rules]
   (tuple 'reply (tuple 'ok 'replaced) new-rules))
  (['get-rules _from rules]
   (tuple 'reply (tuple 'ok rules) rules))
  ([bad-request _from rules]
   (tuple 'reply
          (tuple 'error (tuple 'bad-request bad-request))
          rules)))

(defun handle_cast
  ([(tuple 'crash reason) _rules]
   (erlang:exit reason))
  ([_message rules]
   (tuple 'noreply rules)))

(defun handle_info (_message rules)
  (tuple 'noreply rules))

(defun terminate (_reason _rules)
  'ok)

(defun code_change (_old-version rules _extra)
  (tuple 'ok rules))
