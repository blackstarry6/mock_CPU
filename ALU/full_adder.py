def semi_adder_one(x1,x2):
    s=XOR(x1,x2)
    co=AND(x1,x2)
    return s,co

def full_adder_one(x1,x2,x3):
    s1,co1=semi_adder_one(x1,x2)
    s2,co2=semi_adder_one(x3,s1)
    s=s2
    co=OR(co2,co1)
    return s,co

def full_adder_1(num,CI,*arg):
    list1=[]
    for i in range(num):
        s,co=full_adder_one(arg[2*i],arg[2*i+1],CI)
        CI=co
        list1.append(s)
    list1=list1[::-1]
    print(list1)
    str1="".join(map(str,list1))
    print(str1)
    num=int(str1,2)
    print(num)

def format_uni(num,list1):
    while(len(list1)<num):
        list1.append(0)
    return list1

def format_convert(num,A,B):
    A=bin(A)[2:][::-1]
    B=bin(B)[2:][::-1]
    listA=[int(char) for char in A]
    listB=[int(char) for char in B]
    listA=format_uni(num,listA)
    listB=format_uni(num,listB)
    print(listA,listB)
    arg=[]
    for i in range(num):
        arg.append(listA[i])
        arg.append(listB[i])
    return arg

#num表示输入数据的最大位数，CI表示加法（0），减法（1），输入数据是A和B
def full_adder(num,CI,A,B):
    arg=format_convert(num,A,B)
    full_adder_1(num,CI,*arg)
    
