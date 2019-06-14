# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wagtailcore', '0041_group_collection_permissions_verbose_name_plural')
    ]

    operations = [
        migrations.CreateModel(
            name='GroupCollectionManagementPermission',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('permission_type', models.CharField(choices=[('add', 'Add/edit collections you own'), ('edit', 'Edit any collection'), ('bulk_delete', 'Delete collections with children')], max_length=20, verbose_name='permission type')),
                ('collection', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_manage_permissions', to='wagtailcore.Collection', verbose_name='page')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='collection_manage_permissions', to='auth.Group', verbose_name='group')),
            ],
            options={
                'verbose_name': 'group manage collection permission',
                'verbose_name_plural': 'group manage collection permissions',
            },
        ),
        migrations.AlterUniqueTogether(
            name='groupcollectionmanagementpermission',
            unique_together=set([('group', 'collection', 'permission_type')]),
        ),
    ]
