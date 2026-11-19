from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='escrowaccount',
            name='payout_status',
            field=models.CharField(
                choices=[
                    ('not_started', 'Not Started'),
                    ('pending', 'Pending'),
                    ('failed', 'Failed'),
                    ('success', 'Successful'),
                ],
                default='not_started',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='escrowaccount',
            name='payout_reference',
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='escrowaccount',
            name='paystack_recipient_code',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='escrowaccount',
            name='paystack_transfer_code',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='escrowaccount',
            name='payout_error',
            field=models.TextField(blank=True),
        ),
    ]