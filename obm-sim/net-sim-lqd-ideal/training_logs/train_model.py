import os
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score, recall_score, f1_score
import joblib
import sys

# user input
maxDepth = int(sys.argv[1])
path = str(sys.argv[2])
ports = int(sys.argv[3])

# 1. Load Data
merged = pd.read_csv(path, delim_whitespace=True)

# 2. Separate Drop and Accept scenarios
drops = merged[merged['drop'] == 1]
accepts = merged[merged['drop'] == 0]

# 3. Undersample 'Accepts' to match 'Drops' for TRAINING
n_samples = len(drops)

# We use indices to ensure we know exactly which rows are used
if len(accepts) >= n_samples:
    accepts_sampled = accepts.sample(n=n_samples, random_state=42)
    # --- THE REQUESTED CHANGE ---
    # The "rest of the data" is the accepts that were NOT sampled
    accepts_validation = accepts.drop(accepts_sampled.index)
else:
    # Edge case: If you have fewer accepts than drops, there is no "rest"
    print(f"Warning: Not enough accepts to create a leftover validation set. Using all accepts for train.")
    accepts_sampled = accepts
    accepts_validation = pd.DataFrame(columns=merged.columns) # Empty DF

# 4. Prepare TRAINING Data (50-50 Balanced)
train_data = pd.concat([drops, accepts_sampled])
train_data = train_data.sample(frac=1, random_state=42).reset_index(drop=True)

X_train = train_data.drop('drop', axis=1).values
y_train = train_data['drop'].values

# 5. Prepare VALIDATION Data (Leftover Accepts only)
if not accepts_validation.empty:
    X_val = accepts_validation.drop('drop', axis=1).values
    y_val = accepts_validation['drop'].values
    print(f"Training on: {len(train_data)} samples (Balanced 50/50)")
    print(f"Validating on: {len(accepts_validation)} samples (Leftover Accepts)")
else:
    X_val, y_val = [], []
    print("No data remaining for validation.")

trees = [1,4,8,16]

best_score = -1
best_rf = None
best_ports = -1
best_num_trees = None

print(f"{'Trees':<6} {'Depth':<6} {'Acc':<6} {'FP':<6} {'TN':<6} {'MyScore':<8}")
print("-" * 60)

for numTrees in trees:
    # Train on balanced set
    rf = RandomForestClassifier(max_depth=maxDepth, n_jobs=-1, n_estimators=numTrees, random_state=42)
    rf.fit(X_train, y_train)
    
    # Predict on the "Rest of the Data"
    if len(X_val) > 0:
        y_pred = rf.predict(X_val)
        
        # Force labels=[0,1] to ensure we get a 2x2 matrix even if y_val has no 1s
        cm = confusion_matrix(y_val, y_pred, labels=[0, 1])
        tn, fp, fn, tp = cm.ravel()
        
        # Standard Metrics
        accuracy = accuracy_score(y_val, y_pred)
        
        # RECALL NOTE: Since y_val has NO drops (no positives), Recall is technically undefined (0/0).
        # We focus on False Positives here.
        
        # Custom Score: 
        # Since FN is always 0 here (no real drops to miss), the formula simplifies,
        # but we keep your original logic for consistency.
        denominator = tn - min([(ports)*fn, tn])
        
        if denominator == 0:
            myScore = 0
        else:
            myScore = 1/((tn+fp)/denominator)
            
    else:
        # Fallback if no validation data exists
        accuracy, tn, fp, myScore = 0, 0, 0, 0

    print(f"{numTrees:<6} {maxDepth:<6} {accuracy:.3f}  {fp:<6} {tn:<6} {myScore:.4f}")

    if myScore > best_score:
        best_score = myScore
        best_ports = ports
        best_rf = rf
        best_num_trees = numTrees

# Save the best model
if best_rf:
    joblib.dump(best_rf, f"model_ports{best_ports}_trees{best_num_trees}_depth{maxDepth}.joblib")       
    print(f"\nSaved best model: Trees={best_num_trees}, Score={best_score:.4f}")