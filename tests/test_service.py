# -*- coding: utf-8 -*-

from unittest import mock

import pytest
import sqlalchemy as sa

from .fixtures import AModel, BModel, parametrize, random_alpha


DATASET = [
    {AModel: {'name': random_alpha()},
     BModel: {'name': random_alpha()}},
    {AModel: {'name': random_alpha(),
              'c': {'name': random_alpha()},
              'ds': [{'name': random_alpha()},
                     {'name': random_alpha()}]},
     BModel: {'name': random_alpha()}},
    {AModel: {'id': 1000, 'name': random_alpha()},
     BModel: {'id1': 1000, 'id2': 1000, 'name': random_alpha()}},
]


@pytest.fixture(params=[
    'AModel',
    'BModel'
])
def service(request, db):
    """Test fixture that parametrizes service class instances for model
    classes.
    """
    return getattr(db, request.param)


@pytest.fixture(params=DATASET)
def data_pool(request):
    """Test fixture that parametrizes a common dataset for testing service
    CRUD.
    """
    return request.param


@pytest.fixture(params=DATASET)
def model_pool(request, db):
    """Test fixture that parametrizes model records while inserting them into
    the database first.
    """
    _model = {}
    for model_class, data in request.param.items():
        _model[model_class] = model_class(data)
        db.add(_model[model_class])
    db.commit()

    return _model


@pytest.fixture(params=[
    {AModel: 10, BModel: 10},
])
def models_pool(request, db):
    """Test fixture that parametrizes multiple model records while inserting
    them into the database first. Mainly used for bulk loading of data.
    """
    _models = {}
    for model_class, count in request.param.items():
        _models[model_class] = [model_class({'name': random_alpha()})
                                for _ in range(count)]
        db.add_all(_models[model_class])
    db.commit()

    return _models


def test_new(service, data_pool):
    """Test that new() method returns new model instance."""
    data = data_pool[service.model_class]
    model = service.new(data)

    assert isinstance(model, service.model_class)

    model = dict(model)

    for key, value in data.items():
        assert model[key] == value


def test_get_by_primary_key_value(service, model_pool):
    """Test that SQLService.get returns model given primary key value."""
    model = model_pool[service.model_class]
    ret = service.get(model.identity())
    assert ret is model


def test_get_by_primary_key_dict(service, model_pool):
    """Test that SQLService.get returns model given primary key dict."""
    model = model_pool[service.model_class]
    ret = service.get({col.name: model[col.name]
                       for col in model.pk_columns()})
    assert ret is model


@parametrize('ident', [
    None,
    10,
    -1,
    '',
    [1, 2, 3],
    (1, 2, 3),
    {'id': 10},
    {},
])
def test_get_return_none(service, ident):
    """Test that SQLService.get returns ``None`` when no record found."""
    assert service.get(ident) is None


def test_find(service, models_pool):
    """Test basic find call."""
    models = models_pool[service.model_class]
    ret = service.find()

    assert len(ret) == len(models)
    assert set(ret) == set(models)


def test_find_criteria_as_filter(service, models_pool):
    """Test that find criteria can be passed in as a filter expression."""
    models = models_pool[service.model_class]

    for model in models:
        criteria = (getattr(service.model_class, key) == model[key]
                    for key in model.columns().keys())
        ret = service.find(*criteria)

        assert len(ret) == 1
        assert ret[0] is model


def test_find_criteria_as_filter_by(service, models_pool):
    """Test that find criteria can be passed in as a filter-by dict."""
    models = models_pool[service.model_class]

    for model in models:
        ret = service.find({key: model[key] for key in model.columns().keys()})

        assert len(ret) == 1
        assert ret[0] is model


def test_find_criteria_as_filter_and_filter_by(service, models_pool):
    """Test that find criteria can be passed as both filter expression and
    filter-by dict.
    """
    models = models_pool[service.model_class]

    for model in models:
        ret = service.find({'name': model.name},
                           service.model_class.name == model.name)

        assert len(ret) == 1
        assert ret[0] is model


@parametrize('per_page,page,index', [
    (3, 0, slice(0, 3)),
    (3, None, slice(0, 3)),
    (3, 1, slice(0, 3)),
    (3, 2, slice(3, 6)),
])
def test_find_paginate(service, models_pool, per_page, page, index):
    """Test that find can paginate results."""
    ret = service.find(per_page=per_page, page=page)
    recs = service.query().all()

    assert ret == recs[index]


@parametrize('order_by', [
    {AModel: AModel.name,
     BModel: BModel.name},
    {AModel: AModel.name.desc(),
     BModel: BModel.name.desc()},
    {AModel: sa.text('name'),
     BModel: sa.text('name')},
    {AModel: sa.text('name DESC'),
     BModel: sa.text('name DESC')},
    {AModel: [AModel.name, AModel.id],
     BModel: [BModel.name, BModel.id1]},
])
def test_find_order_by(service, models_pool, order_by):
    """Test that find and order results."""
    order_by = order_by[service.model_class]

    recs = (service.query()
            .order_by(*([order_by] if not isinstance(order_by, list)
                        else order_by))
            .all())
    ret = service.find(order_by=order_by)

    assert ret == recs


def test_insert_model(db, service, data_pool):
    """Test service insert."""
    data = data_pool[service.model_class]
    model = service.new(data)

    service.save(model)

    dbmodels = db.query(service.model_class).all()

    assert len(dbmodels) == 1
    assert model is dbmodels[0]


def test_insert_all_models(db, service, data_pool):
    """Test service insert."""
    if service.model_class is AModel:
        return

    data = data_pool[service.model_class]

    for col in service.model_class.pk_columns():
        if col.name in data:
            del data[col.name]

    models = [service.new(item) for item in [data] * 5]

    service.save(models)

    dbmodels = db.query(service.model_class).all()

    assert len(models) == len(dbmodels)
    assert set(models) == set(dbmodels)


def test_update_model(db, service, model_pool):
    """Test service update."""
    model = model_pool[service.model_class]
    new_values = {'name': random_alpha()}
    model.update(new_values)

    service.save(model)

    dbmodels = db.query(service.model_class).all()

    assert len(dbmodels) == 1

    dbmodel = dbmodels[0]

    assert model is dbmodel

    for key, value in new_values.items():
        assert dbmodel[key] == value


def test_update_all_models(db, service, models_pool):
    """Test service update all."""
    models = models_pool[service.model_class]
    new_values = {'name': random_alpha()}

    for model in models:
        model.update(new_values)

    service.save(models)

    dbmodels = db.query(service.model_class).all()

    assert len(models) == len(dbmodels)
    assert set(models) == set(dbmodels)

    for model in dbmodels:
        for key, value in new_values.items():
            assert model[key] == value


def test_save(db, service, models_pool, data_pool):
    """Test service add method."""
    data = models_pool[service.model_class] + [data_pool[service.model_class]]

    service.save(data)

    dbmodels = db.query(service.model_class).all()

    assert len(dbmodels) == len(data)


@parametrize('data', [
    {AModel: [{'id': 1}, {'id': 1}],
     BModel: [{'id1': 1, 'id2': 2}, {'id1': 1, 'id2': 2}]},
])
def test_save_duplicate_primary_key_error(db, service, data):
    """Test that IntegrityError raised when duplicate primary key records are
    added at the same time.
    """
    data = data[service.model_class]

    with pytest.raises(sa.exc.IntegrityError):
        service.save(data)


def test_save_upsert_dict(db, service, models_pool):
    """Test that service add upserts existing records."""
    models = models_pool[service.model_class]
    data = [dict(model) for model in models]

    ret = service.save(data)
    dbmodels = db.query(service.model_class).all()

    assert len(ret) == len(models) == len(dbmodels)
    assert set(ret) == set(models) == set(dbmodels)


def test_destroy_primary_key(db, service, model_pool):
    """Test that model is deleted using primary key."""
    model = model_pool[service.model_class]
    ident = model.identity()
    count = service.destroy(ident)

    assert service.query().count() == 0
    assert count == 1


def test_destroy_dict(db, service, model_pool):
    """Test that a single dict is deleted."""
    model = model_pool[service.model_class]
    data = dict(model)
    count = service.destroy(data)

    assert service.query().count() == 0
    assert count == 1


def test_destroy_model(db, service, model_pool):
    """Test that a single model is deleted."""
    model = model_pool[service.model_class]
    count = service.destroy(model)

    assert service.query().count() == 0
    assert count == 1


def test_destroy_many_primary_keys(db, service, models_pool):
    """Test that model is deleted using primary key."""
    models = models_pool[service.model_class]
    idents = [model.identity() for model in models]
    count = service.destroy(idents)

    assert service.query().count() == 0
    assert count == len(models)


def test_destroy_many_dicts(db, service, models_pool):
    """Test that many dicts are deleted."""
    models = models_pool[service.model_class]
    data = [dict(model) for model in models]
    count = service.destroy(data)

    assert service.query().count() == 0
    assert count == len(models)


def test_destroy_many_models(db, service, models_pool):
    """Test that many models are deleted."""
    models = models_pool[service.model_class]
    count = service.destroy(models)

    assert service.query().count() == 0
    assert count == len(models)