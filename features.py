"""Build an unfitted transformer. Call fit ONLY on the training partition."""
def make_transformer(numeric, categorical, target=None):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    names = list(numeric) + list(categorical)
    if not names or len(names) != len(set(names)) or target in names:
        raise ValueError('Select distinct predictors and exclude the target')
    return ColumnTransformer([
        ('numeric', Pipeline([('impute', SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True)),
                              ('scale', StandardScaler())]), numeric),
        ('categorical', Pipeline([('impute', SimpleImputer(strategy='constant', fill_value='__MISSING__', keep_empty_features=True)),
                                  ('encode', OneHotEncoder(handle_unknown='ignore', max_categories=100, sparse_output=True))]), categorical)
    ], remainder='drop', sparse_threshold=1.0)
