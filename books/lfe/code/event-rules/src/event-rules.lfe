(defmodule event-rules
  "Data-first kernel for the book's Event Routing DSL project."
  (export (route 2)
          (sample-rules 0)
          (sample-event 0)))

(defun route
  ([(= event (tuple 'event _ _ _)) rules]
   (route-event event rules))
  ([bad-event _]
   (tuple 'error (tuple 'bad-event bad-event))))

(defun route-event
  ([_event ()]
   (tuple 'error 'no-route))
  ([(tuple 'event level _service _payload)
    (cons (tuple 'when-level level destination) _rest)]
   (tuple 'ok destination))
  ([(tuple 'event _level service _payload)
    (cons (tuple 'when-service service destination) _rest)]
   (tuple 'ok destination))
  ([(tuple 'event _level _service _payload)
    (cons (tuple 'otherwise destination) _rest)]
   (tuple 'ok destination))
  ([event (cons (tuple 'when-level _ _) rest)]
   (route-event event rest))
  ([event (cons (tuple 'when-service _ _) rest)]
   (route-event event rest))
  ([_event (cons bad-rule _rest)]
   (tuple 'error (tuple 'bad-rule bad-rule))))

(defun sample-rules ()
  (list
   (tuple 'when-level 'critical 'pager)
   (tuple 'when-service 'billing 'billing-queue)
   (tuple 'otherwise 'archive)))

(defun sample-event ()
  (tuple 'event 'critical 'edge '#"disk full"))
