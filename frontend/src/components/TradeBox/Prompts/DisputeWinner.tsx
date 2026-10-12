import React from 'react';
import { useTranslation } from 'react-i18next';
import { List, ListItem, Divider, Typography } from '@mui/material';

interface Props {
  /** The order's coordinator's contact (its own email, or another way to reach it). */
  contact?: string;
}

// Each coordinator answers for its own disputes: the text names its contact, not RoboSats'.
const withContact = (text: string, contact?: string): string =>
  text.replace(/robosats@protonmail\.com|kilombino@proton\.me/g, contact ?? 'kilombino@proton.me');

export const DisputeWinnerPrompt = ({ contact }: Props): React.JSX.Element => {
  const { t } = useTranslation();

  return (
    <List dense={true}>
      <Divider />
      <ListItem>
        <Typography variant='body2'>
          {withContact(
            t(
              'You can claim the dispute resolution amount (escrow and fidelity bond) from your profile rewards. If there is anything the staff can help with, do not hesitate to contact to robosats@protonmail.com (or via your provided burner contact method).',
            ),
            contact,
          )}
        </Typography>
      </ListItem>
    </List>
  );
};

export default DisputeWinnerPrompt;
