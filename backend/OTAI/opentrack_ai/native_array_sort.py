"""Finite-position projection of Foundation _NSMergeSort at 0x32011208.

Foundation SHA256 3f33e3e33d144ef265a0e0d7b87b54ec147cdd6aae2838d3977a5763541b1b89.
Equal keys interleave left/right during a merge. The already-ordered shortcut
is selected once from the top-level count > 63 and propagated recursively.
Replacing this with Python's stable sort changes native duplicate-row lookup.
"""


def sort_by_position(values):
    optimize=len(values)>63

    def compare(first,second):
        a,b=first['position_m'],second['position_m']
        return 1 if a>b else -1 if a<b else 0

    def merge(items):
        count=len(items)
        if count<2:return list(items)
        if count==2:return list(items) if compare(items[0],items[1])<=0 else [items[1],items[0]]
        if count==3:
            a,b,c=items
            if compare(a,b)<=0:
                if compare(b,c)<=0:return [a,b,c]
                return [a,c,b] if compare(a,c)<=0 else [c,a,b]
            if compare(b,c)<=0:return [b,a,c] if compare(a,c)<=0 else [b,c,a]
            return [c,b,a]
        middle=count//2;left=merge(items[:middle]);right=merge(items[middle:])
        if optimize and compare(left[-1],right[0])<=0:return left+right
        result=[];i=j=0
        while i<len(left) and j<len(right):
            relation=compare(left[i],right[j])
            if relation<=0:result.append(left[i]);i+=1
            if relation>=0:result.append(right[j]);j+=1
        return result+left[i:]+right[j:]

    return merge(values)
