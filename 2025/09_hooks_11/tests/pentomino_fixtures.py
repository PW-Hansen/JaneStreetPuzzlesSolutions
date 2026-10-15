from functions.hooks import HookSearch, hook_cells, partition_borders
from functions.model import Puzzle


def example_puzzle():
    puzzle = Puzzle('Pentomino example', 5, 5)
    puzzle.data['entries'] = {
        '2,0':'3', '2,1':'2', '3,2':'1', '1,2':'3', '2,3':'5', '0,4':'4', '4,4':'4',
        '4,-1':'Y', '0,-1':'U', '1,5':'U', '3,5':'F',
    }
    search = HookSearch(puzzle.data)
    list(search.run())
    puzzle.set_hook_analysis(search, 0.01)
    return puzzle


def nested_context_data(known=True):
    puzzle = Puzzle('Nested', 5, 5)
    puzzle.data['entries'] = {f'{row},0':str(row+1) for row in range(5)} if known else {'0,0':'1'}
    hooks = [[(0,0)]]
    for size in range(2, 6):
        hooks.append(hook_cells((0,0,size-1), (0,0,size)))
    return puzzle.data, partition_borders(hooks, 5, 5)


def finish(generator):
    while True:
        try:
            next(generator)
        except StopIteration as stopped:
            return stopped.value


def nine_cell_side_pentomino_puzzle():
    from functions.pentominoes import PentominoSearch
    puzzle = Puzzle('Remaining example', 9, 9)
    puzzle.data['entries'] = {f'{row},0':str(row+1) for row in range(9)}
    puzzle.data['entries']['0,-1'] = 'I'
    hooks = HookSearch(puzzle.data)
    list(hooks.run())
    puzzle.set_hook_analysis(hooks, 0.01)
    pentominoes = PentominoSearch(puzzle.data)
    list(pentominoes.run())
    puzzle.set_pentomino_analysis(pentominoes, 0.01)
    return puzzle
