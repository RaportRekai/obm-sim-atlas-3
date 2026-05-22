import os
import re
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score, recall_score, f1_score, ConfusionMatrixDisplay
from sklearn.model_selection import RandomizedSearchCV, train_test_split
from scipy.stats import randint
from sklearn.tree import export_graphviz
from IPython.display import Image
# import graphviz
# from sklearn.externals import joblib
import joblib
import sys
# user input

maxDepth = int(sys.argv[1])
path = str(sys.argv[2])
ports = int(sys.argv[3])
#model = str(sys.argv[3])


merged = pd.read_csv(path, delim_whitespace=True)

X = merged.drop('drop', axis=1).values
y = merged['drop'].values

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

trees=[1,4]#[1,2,4,8,16,32,64,128]

best_score = -1
best_rf = None
best_ports = -1
best_num_trees = None

for numTrees in trees:
    rf = RandomForestClassifier(max_depth=maxDepth, n_jobs=-1,n_estimators=numTrees)
    rf.fit(X_train, y_train)
    #joblib.dump(rf,f"model_ports{ports}_trees{numTrees}_depth{maxDepth}.joblib")
    y_pred = rf.predict(X_test)
    
    cm = confusion_matrix(y_test, y_pred)

    try:
        accuracy = accuracy_score(y_test, y_pred)
    except:
        accuracy = 1
    if (accuracy==0):
        accuracy = 1
    try:
        precision = precision_score(y_test, y_pred)
    except:
        precision = 1
    if (precision==0):
        precision = 1
    try:
        recall = recall_score(y_test, y_pred)
    except:
        recall = 1
    if (recall==0):
        recall = 1
    try:
        f1score = f1_score(y_test,y_pred)
    except:
        f1score = 1
    if (f1score==0):
        f1score = 1
        
    try:
        tn = cm[0][0]
        fp = cm[0][1]
        fn = cm[1][0]
        tp = cm[1][1]
        myScore = 1/((tn+fp)/(tn - min([(ports)*fn,tn])))
    except:
        myScore=1
    if myScore==0:
        myScore=1
    print(accuracy,precision,recall,f1score,numTrees,maxDepth,myScore)
    
    if myScore > best_score:
        best_score = myScore
        best_ports = ports
        best_rf = rf
        best_num_trees = numTrees
joblib.dump(best_rf,f"model_ports{best_ports}_trees{best_num_trees}_depth{maxDepth}.joblib")       
print("Saved best model:", best_num_trees, best_score)