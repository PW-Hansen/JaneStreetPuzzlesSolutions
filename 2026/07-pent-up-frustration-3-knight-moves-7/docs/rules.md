# Puzzle Rules
The board above has been tiled with the 12 pentominoes (plus a 2-by-2 tetromino) into 13 regions. Think of each of these 13 regions as constructed out of 1-by-1-by-1 cubes. We need to add a tower to each region. A tower is an additional size-1 cube placed on one of a region’s squares.

After adding these towers, place a knight at the bottom-left square. It then proceeds to make knight’s moves until it has visited all the towers. It never visits the same space twice. (A move on this board involves travelling 0 units in one dimension, 1 in another, and 2 in the third. The knight is allowed to “pass through” towers as it moves.)

But there’s a catch: As you can see, the knight starts with a score of 0. On its Nth move, its score increases by N if the move is to a location at the same altitude as the square it moved from. If, instead, it moves up, the score is multiplied by N. And finally, if it moves down, the score is divided by N. This last type of move is only allowed if the score is evenly divisible by N.

Every three moves, up until move #18, the knight wrote down its score upon arriving at a given square. From then on it only wrote down its score every K moves, for some larger value K. Using this information, can you reconstruct the knight’s path?

## Answer Key Generation
After filling all the remaining visited squares with the missing score values, find the unvisited squares. For each of these squares, compute the sum of the scores in any orthogonally adjacent squares that were part of the knight’s path. The answer to this puzzle is the sum of these “neighbor sums” from the unvisited squares.

(Credit: Jane Street)