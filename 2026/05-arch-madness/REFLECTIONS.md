# Reflections on this project
I worked on this project over two days, and by the time I stopped on the first day I had something that could solve the full puzzle... in about 10 minutes. If it was given a specific order to analyze clues in that I had discovered worked well.

This was entirely too long, and even that only came after I prompted Codex to not consider the full 5 possibilities (4 possible arc orientation + no arc) for cells when analyzing clues (cells with numbers in them), but instead to consider simplified (positive diagonal, negative diagonal, no arc) arcs.

I did not consider a solving time acceptable, so I suggested other ways I thought could potentially speed up the search, but nothing seemed to make things better. Most of my suggestions led to a worse performance. By the second day, one improvement I did was that if there were multiple valid solutions for a clue, low-depth sanity checks should be run on clues next to the solution to see if any of the accepted state for a specific clue would break another clue, in which case the accepted state would be rejected. This did help, but not anywhere near enough. I eventually asked Codex for suggestions, but none of the three suggestions it provided led to a performance increase when applied to the full puzzle.

After that, I spent some time simply playing around with potential arc placements on an empty grid, and realized that a region must have an even number of shared cell borders with the edge of the grid. Using that insight, I instructed Codex to create a greedy search mode so that when a clue was analyzed, it would try to create the largest possible region when it gained one region border, try to disprove that, then move on to the second-largest, and so on.

Furthermore, I had explicitly instructed Codex to allow for the possibility that a region could be created from a single smooth piece, meaning that if it was considering a clue with a value of 25, it would need to entertain the possibility that the clue would be part of a region with an area of 25, but whose perimeter was a single continuously differentible piece. I instructed Codex to also make the greedy search mode require that regions be composed of at least 3 distinct perimeter pieces.

And when I ran that greedy search mode with the previously mentioned order, it solved the puzzle in a bit more than 3 seconds.

After sitting down and thinking further about it, I proved to my own satisfaction that it was impossible to create a region with less than 3 distinct perimeter pieces, after which I moved the that rule from the greedy search to the regular search, which made even the non-greedy solution time plummet massively.

This has been a valuable lesson about thinking very carefully about the problem at hand and trying to determine restrictions, requirements, or rules which are not immediately clear, rather than just handing an AI a task and tell it to get going without proper consideration.