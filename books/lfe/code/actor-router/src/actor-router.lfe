(defmodule actor-router
  "Pre-OTP process wrapper around the Event Routing DSL kernel."
  (export (start 1)
          (call 3)
          (route 3)
          (replace-rules 3)
          (get-rules 2)
          (stop 2)
          (crash 2)
          (loop 1)))

(defun start (rules)
  (spawn 'actor-router 'loop (list rules)))

(defun call (pid request timeout)
  (let ((ref (erlang:make_ref)))
    (! pid (tuple 'call (self) ref request))
    (receive
      ((tuple 'reply ref result)
       result)
      (after timeout
        (tuple 'error 'timeout)))))

(defun route (pid event timeout)
  (call pid (tuple 'route event) timeout))

(defun replace-rules (pid rules timeout)
  (call pid (tuple 'replace-rules rules) timeout))

(defun get-rules (pid timeout)
  (call pid 'get-rules timeout))

(defun stop (pid timeout)
  (call pid 'stop timeout))

(defun crash (pid reason)
  (! pid (tuple 'cast (tuple 'crash reason)))
  'ok)

(defun loop (rules)
  (receive
    ((tuple 'call from ref (tuple 'route event))
     (! from (tuple 'reply ref (event-rules:route event rules)))
     (loop rules))
    ((tuple 'call from ref (tuple 'replace-rules new-rules))
     (! from (tuple 'reply ref (tuple 'ok 'replaced)))
     (loop new-rules))
    ((tuple 'call from ref 'get-rules)
     (! from (tuple 'reply ref (tuple 'ok rules)))
     (loop rules))
    ((tuple 'call from ref 'stop)
     (! from (tuple 'reply ref 'ok))
     'ok)
    ((tuple 'call from ref bad-request)
     (! from (tuple 'reply ref
                    (tuple 'error (tuple 'bad-request bad-request))))
     (loop rules))
    ((tuple 'cast (tuple 'crash reason))
     (erlang:exit reason))
    (_unknown
     (loop rules))))
