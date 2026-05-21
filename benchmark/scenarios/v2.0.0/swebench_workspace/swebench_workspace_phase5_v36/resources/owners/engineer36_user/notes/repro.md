# Reproduction Notes

Instance: scikit-learn__scikit-learn-13779
Repo: scikit-learn/scikit-learn
Issue digest: Voting estimator will fail at fit if weights are passed and an estimator is None
Because we don't check for an estimator to be `None` in `sample_weight` support, `fit` is failing`.

```python
    X, y = load_iris(return_X_y=True)
    voter = VotingClassifier(
        estimators=[('lr', LogisticRegression()),
                    ('rf', RandomForestClassifier())]
    )
    voter.fit(X, y, sample_weight=np.ones(y.shape))
    voter.set_params(lr=None)
    voter.fit(X, y, sample_weight=np.ones(y.shape))
```

```
AttributeError: 'NoneType' object has no attribute 'fit'
```

Required file evidence: sklearn/ensemble/voting.py
Target tests to record before review: sklearn/ensemble/tests/test_voting.py::test_none_estimator_with_weights[X0-y0-voter0], sklearn/ensemble/tests/test_voting.py::test_none_estimator_with_weights[X1-y1-voter1]
Use these notes as the source of truth for the target tests and issue symptom before asking for review.
