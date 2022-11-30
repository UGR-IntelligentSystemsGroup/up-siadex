(define (domain bloques)
(:requirements
  :typing
  :fluents
  :derived-predicates
  :negative-preconditions
  :htn-expansion)

(:types
  bloque superficie - object)

(:constants mesa - superficie) 

(:predicates
  (manovacia)
  (libre ?x - bloque)
  (cogido ?x - bloque)
  (sobremesa ?x - bloque)
  (sobre ?x ?y - bloque)
  (igual ?x ?y)
  (distinto ?x ?y))

;; Regla para "derivar" (determinar) si dos variables son distintas.
;; Las reglas de este tipo se corresponden con la estructura 
;; (:derived <consecuente> <condición>)
;; <consecuente> debe ser un único predicado
;; <condición> debe ser una expresión lógica
;; la interpretación de estas reglas es como sigue:
;; si en el estado actual <condicion> es cierta, entonces <consecuente> es cierto
;; Es utilizada de forma general para representar con un sólo predicado una 
;; condición o cálculo complejo

(:derived 
  (distinto ?x ?y) (not (igual ?x ?y)))

;; el consecuente "vacío" se representa como "()" y significa "siempre verdad"
(:derived
  (igual ?x ?x) ())


(:task sobre
 :parameters (?x - bloque ?y - object)
 (:method poner_encima
  :precondition () ; vacío
  :tasks (
          (limpiar ?x)
          (limpiar ?y)
          (colocar ?x ?y)
          )
))

(:task limpiar
 :parameters (?x - bloque)
 (:method limpiar_mesa
  :precondition ((igual ?x mesa))
  :tasks())
 (:method limpiar_libre
  :precondition ((libre ?x))
  :tasks ())
 (:method limpiar_ocupado
  :precondition (sobre ?y ?x)
  :tasks ((limpiar ?y)(colocar ?y mesa))))
  
(:task colocar
 :parameters (?x - bloque ?y - object)
 (:method colocar
  :precondition ()
  :tasks ((primero-coge ?x)(despues-deja ?x ?y))))

(:task primero-coge
 :parameters (?x - bloque)
 (:method cogelo_de_la_mesa
  :precondition ((sobremesa ?x))
  :tasks ((coger ?x)))
 (:method cogelo_de_la_pila
  :precondition (sobre ?x ?y)
  :tasks ((desapilar ?x ?y))))

(:task despues-deja
 :parameters (?x - bloque ?y - object)
 (:method dejalo_en_la_mesa
  :precondition ((igual ?y mesa))
  :tasks ((dejar ?x)))
 (:method dejalo_en_la_pila
  :precondition ((distinto ?y mesa))
  :tasks ((apilar ?x ?y))))


(:action coger
 :parameters (?x - bloque)
 :precondition (and (sobremesa ?x)(libre ?x)(manovacia))
 :effect (and (not (sobremesa ?x)) (not (libre ?x))(not (manovacia))
	      (cogido ?x)))

(:action dejar
 :parameters (?x - bloque)
 :precondition (cogido ?x)
 :effect (and (sobremesa ?x) (libre ?x) (manovacia)
              (not (cogido ?x))))

(:action apilar
 :parameters (?x ?y - bloque)
 :precondition (and (cogido ?x)(libre ?y))
 :effect (and (not (cogido ?x)) (not (libre ?y)) (libre ?x) (sobre ?x ?y) (manovacia)))

(:action desapilar
 :parameters (?x ?y - bloque)
 :precondition (and (manovacia) (libre ?x) (sobre ?x ?y))
 :effect  (and (cogido ?x) (libre ?y) (not (libre ?x)) (not (sobre ?x ?y)) (not (manovacia))))
)
