# Algorytm balansujący ruch na kontrolerach SDN

## Wysoko-poziomowy diagram działania

![diagram](./controller_balancing_diagram_dark.png#gh-dark-mode-only)
![diagram](./controller_balancing_diagram_dark.png#gh-light-mode-only)

## Opis

Kontrolery przesyłają okresowo obliczony load operacji na sobie do super-kontrolera/kontroler-mastera.
Super-kontroler mając informację z wszystkich kontrolerów sprawdza czy nie zachwiana
jest równowaga (oczywiście w ustalonym progu) w podległych mu kontrolerach,
przesyła do obładowanego kontrolera, żeby ten przesłał mu trochę ruchu,
żeby się odciążyć i super kontroler przekazuje te operacje innemu, mniej załadowanemu kontrolerowi.
Każdy kontroler wylicza load na bazie macierzy przepływów między każdym podległym mu switchem.

## Bibliografia

* Selvi, H., Gur, G., & Alagoz, F. (2016). Cooperative load balancing for hierarchical SDN controllers. 2016 IEEE 17th International Conference on High Performance Switching and Routing (HPSR). doi:10.1109/hpsr.2016.7525646
