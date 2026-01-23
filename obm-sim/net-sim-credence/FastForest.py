import numpy as np

class FastForest:
    def __init__(self, sklearn_model):
        """
        Extracts the raw arrays from the sklearn model into simple Python lists.
        """
        self.trees = []
        
        # Loop through every tree (estimator) in the random forest
        for estimator in sklearn_model.estimators_:
            tree_structure = estimator.tree_
            
            # We extract 4 key arrays for each tree
            # 1. The feature index to check at each node (0, 1, 2, or 3)
            # 2. The threshold value to compare against
            # 3. The index of the left child node
            # 4. The index of the right child node
            # 5. The final prediction value at leaf nodes
            
            tree_data = {
                'feature': tree_structure.feature.tolist(),
                'threshold': tree_structure.threshold.tolist(),
                'children_left': tree_structure.children_left.tolist(),
                'children_right': tree_structure.children_right.tolist(),
                'value': tree_structure.value.tolist()
            }
            self.trees.append(tree_data)

    def predict(self, f0, f1, f2, f3):
        """
        Runs the decision path.
        f0: Queue Length
        f1: Shared Occupancy
        f2: Avg Queue Length
        f3: Avg Shared Occupancy
        """
        votes_for_drop = 0
        total_trees = len(self.trees)
        
        # Ask every tree for its opinion
        for tree in self.trees:
            node = 0  # Start at the root (node 0)
            
            # Traverse until we hit a leaf node
            # In sklearn, a node is a leaf if children_left[node] == -1
            while tree['children_left'][node] != -1:
                
                # Identify which feature this node cares about
                feature_idx = tree['feature'][node]
                
                # Map index to the actual input value
                # (Hardcoded if/else is faster than list lookup here)
                if feature_idx == 0:
                    val = f0
                elif feature_idx == 1:
                    val = f1
                elif feature_idx == 2:
                    val = f2
                else:
                    val = f3
                
                # Make the decision: Go Left or Right?
                if val <= tree['threshold'][node]:
                    node = tree['children_left'][node]
                else:
                    node = tree['children_right'][node]
            
            # We are at a leaf node. Check the vote.
            # 'value' looks like [[count_accept, count_drop]]
            # Index 1 is usually the positive class (Drop) in your training
            counts = tree['value'][node][0]
            
            if counts[1] > counts[0]:
                votes_for_drop += 1
        
        # Majority Vote
        if votes_for_drop > (total_trees / 2):
            return 1  # DROP
        else:
            return 0  # ACCEPT