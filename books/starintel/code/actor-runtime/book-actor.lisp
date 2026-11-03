;;;; Project 3: a deliberately small local StarIntel actor.
;;;;
;;;; This file is loaded only by the book's pinned upstream test harness.  It
;;;; uses StarIntel's current actor/dispatch API instead of reimplementing the
;;;; router, scheduler, persistence layer, or Rabbit transport.

(defpackage :starintel-book.actor-lab
  (:use :cl)
  (:export
   #:*book-actor*
   #:arm-book-handler-failure
   #:book-actor-name
   #:book-failure-armed-p
   #:book-receipts
   #:reset-book-receipts
   #:start-book-actor))

(in-package :starintel-book.actor-lab)

(defparameter *book-actor* nil)
(defparameter *book-receipts* nil)
(defparameter *fail-next-envelope* nil)
(defparameter *receipt-lock* (bt:make-lock "starintel-book-actor-receipts"))

(defun book-actor-name ()
  "Return the registry identity used by the teaching actor."
  "book-audit")

(defun reset-book-receipts ()
  "Clear receipts and any pending test-only handler fault."
  (bt:with-lock-held (*receipt-lock*)
    (setf *book-receipts* nil
          *fail-next-envelope* nil)))

(defun book-receipts ()
  "Return a copy of the teaching actor's sanitized receipt records."
  (bt:with-lock-held (*receipt-lock*)
    (copy-tree (reverse *book-receipts*))))

(defun arm-book-handler-failure ()
  "Cause exactly the next valid target envelope to raise inside the handler.

This switch exists only for the book's failure lab.  It leaves StarIntel and
Sento failure handling untouched so the test observes the real pinned runtime
boundary rather than a book-side substitute."
  (bt:with-lock-held (*receipt-lock*)
    (setf *fail-next-envelope* t)))

(defun book-failure-armed-p ()
  "Return true while the one-shot failure injection is still pending."
  (bt:with-lock-held (*receipt-lock*)
    *fail-next-envelope*))

(defun consume-book-handler-failure-p ()
  (bt:with-lock-held (*receipt-lock*)
    (prog1 *fail-next-envelope*
      (setf *fail-next-envelope* nil))))

(defun record-target-envelope (message)
  "Record only routing metadata needed by the book's executable lab."
  (unless (typep message 'star.actors:target-dispatch-envelope)
    (error "book-audit expected TARGET-DISPATCH-ENVELOPE, got ~s"
           (type-of message)))
  (when (consume-book-handler-failure-p)
    (error "book-audit injected handler failure"))
  (let* ((record (star.actors:target-dispatch-envelope-record message))
         (receipt
           (list :target (star.actors:target-record-target record)
                 :schedule-id
                 (star.actors:target-dispatch-envelope-schedule-id message)
                 :execution-id
                 (star.actors:target-dispatch-envelope-execution-id message)
                 :trace-id
                 (star.actors:target-dispatch-envelope-trace-id message))))
    (bt:with-lock-held (*receipt-lock*)
      (push receipt *book-receipts*))
    :recorded))

(defun start-book-actor (system)
  "Create and register the teaching actor as one explicit startup operation.

The current StarIntel DEFINE-ACTOR macro creates a startup hook but does not
perform registry insertion.  This project keeps actor creation and registry
insertion adjacent so a reader cannot accidentally build an unreachable local
actor."
  (setf *book-actor*
        (sento.actor-context:actor-of
         system
         :name (book-actor-name)
         :receive #'record-target-envelope))
  (star.actors:register-actor (book-actor-name) *book-actor*)
  *book-actor*)
